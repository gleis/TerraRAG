#!/usr/bin/env bash
set -euo pipefail
image=${1:-terrarag-ollama:review}
original=ollama/ollama:0.40.15@sha256:0e59999e0e8f9fd4e704bd788a89b7e4cad399367fb1365f8c102ac662288761
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
fingerprint='cd /usr/lib/ollama; find . -type f -exec sha256sum {} \; | LC_ALL=C sort; find . -type f -exec stat -c "%a %n" {} \; | LC_ALL=C sort; find . -type l -exec sh -c '\''for p do printf "%s -> %s\n" "$p" "$(readlink "$p")"; done'\'' sh {} + | LC_ALL=C sort'
docker run --rm --entrypoint sh "$original" -c "$fingerprint" > "$stage/original.txt"
docker run --rm --entrypoint sh "$image" -c "$fingerprint" > "$stage/candidate.txt"
diff -u "$stage/original.txt" "$stage/candidate.txt"
docker run --rm --entrypoint sh "$image" -ec '
  test "$(readlink -f /bin/ollama)" = /usr/bin/ollama
  test -s /lib/apk/db/installed
  ! command -v nscd
  loader=/usr/lib/ld-linux-x86-64.so.2
  case "$(uname -m)" in aarch64) loader=/usr/lib/ld-linux-aarch64.so.1;; esac
  "$loader" --list /usr/bin/ollama
  dirs=$(find /usr/lib/ollama -type d | paste -sd : -)
  export LD_LIBRARY_PATH="$dirs:${LD_LIBRARY_PATH:-}"
  find /usr/lib/ollama -type f | while IFS= read -r file; do
    magic=$(head -c 4 "$file" | od -An -tx1 | tr -d " \n")
    [ "$magic" = 7f454c46 ] || continue
    machine=$(dd if="$file" bs=1 skip=18 count=2 2>/dev/null | od -An -tx1 | tr -d " \n")
    kind=$(dd if="$file" bs=1 skip=16 count=2 2>/dev/null | od -An -tx1 | tr -d " \n")
    # CUDA code objects and relocatable build objects are preserved data, not
    # host programs that the Linux dynamic loader can execute.
    case "$machine:$kind" in 3e00:0200|3e00:0300|b700:0200|b700:0300) ;; *) continue;; esac
    # Runtime-injected NVIDIA driver libraries are an explicit external
    # precondition. Every other missing native dependency fails this check.
    output=$("$loader" --list "$file" 2>&1) || {
      printf "%s\n" "$output"
      printf "%s\n" "$output" | grep -Eq "(libcuda.so.1|libnvidia-ml.so.1): cannot open shared object file" || exit 1
      printf "External NVIDIA driver required: %s\n" "$file"
      continue
    }
    printf "Native closure: %s\n%s\n" "$file" "$output"
  done
'
echo 'Complete upstream native payload hashes, modes and symlinks preserved'
