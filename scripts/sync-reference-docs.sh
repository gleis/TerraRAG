#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DOC_ROOT=${REFERENCE_DOCS_ROOT:-$PROJECT_DIR/reference-docs}
TERRAFORM_VERSION=v1.17.x
TERRAFORM_COMMIT=965264c6e76c012c7bdc40a0a4d2f5456b49bce0
TERRAGRUNT_VERSION=v1.2.1
TERRAGRUNT_COMMIT=ed85b42a24b52494212b622cd45cb349cec53a3b
TEMP_DIR=$(mktemp -d)

cleanup() {
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT INT TERM

git init --quiet "$TEMP_DIR/hashicorp-docs"
git -C "$TEMP_DIR/hashicorp-docs" remote add origin https://github.com/hashicorp/web-unified-docs.git
git -C "$TEMP_DIR/hashicorp-docs" sparse-checkout init --cone
git -C "$TEMP_DIR/hashicorp-docs" fetch --quiet --depth 1 --filter=blob:none origin "$TERRAFORM_COMMIT"
git -C "$TEMP_DIR/hashicorp-docs" checkout --quiet --detach FETCH_HEAD
git -C "$TEMP_DIR/hashicorp-docs" sparse-checkout set "content/terraform/$TERRAFORM_VERSION/docs/language"
actual_terraform_commit=$(git -C "$TEMP_DIR/hashicorp-docs" rev-parse HEAD)
if [ "$actual_terraform_commit" != "$TERRAFORM_COMMIT" ]; then
  echo "Terraform documentation commit changed: expected $TERRAFORM_COMMIT, got $actual_terraform_commit" >&2
  echo "Review the upstream changes and update the pin intentionally." >&2
  exit 1
fi

git clone --quiet --depth 1 --branch "$TERRAGRUNT_VERSION" --filter=blob:none --sparse \
  https://github.com/gruntwork-io/terragrunt.git "$TEMP_DIR/terragrunt-docs"
git -C "$TEMP_DIR/terragrunt-docs" sparse-checkout set docs/src/content/docs
actual_terragrunt_commit=$(git -C "$TEMP_DIR/terragrunt-docs" rev-parse HEAD)
if [ "$actual_terragrunt_commit" != "$TERRAGRUNT_COMMIT" ]; then
  echo "Terragrunt documentation commit changed: expected $TERRAGRUNT_COMMIT, got $actual_terragrunt_commit" >&2
  exit 1
fi

STAGE="$TEMP_DIR/stage"
mkdir -p "$STAGE/terraform/$TERRAFORM_VERSION" "$STAGE/terragrunt/$TERRAGRUNT_VERSION"
rsync -a "$TEMP_DIR/hashicorp-docs/content/terraform/$TERRAFORM_VERSION/docs/language/" \
  "$STAGE/terraform/$TERRAFORM_VERSION/language/"
rsync -a "$TEMP_DIR/terragrunt-docs/docs/src/content/docs/" \
  "$STAGE/terragrunt/$TERRAGRUNT_VERSION/docs/"

cat > "$STAGE/CORPUS.md" <<EOF
# TerraRAG Official Reference Corpus

This local corpus contains official, version-pinned product documentation.

- Terraform language documentation: $TERRAFORM_VERSION
  - Source: https://github.com/hashicorp/web-unified-docs
  - Commit: $TERRAFORM_COMMIT
- Terragrunt documentation: $TERRAGRUNT_VERSION
  - Source: https://github.com/gruntwork-io/terragrunt
  - Commit: $TERRAGRUNT_COMMIT

The corpus is read-only at runtime. Refresh it only through scripts/sync-reference-docs.sh after reviewing upstream changes and updating the pinned commits.
EOF

mkdir -p "$DOC_ROOT"
rsync -a --delete "$STAGE/" "$DOC_ROOT/"
count=$(find "$DOC_ROOT" -type f \( -name '*.md' -o -name '*.mdx' \) | wc -l | tr -d ' ')
echo "Synced $count official documentation pages into $DOC_ROOT"
