FROM golang:1.27.3-bookworm@sha256:dc0963f32053e4bc451d24d87e3892d42d01021b61f093e98eb95c0352bb84b0 AS build
WORKDIR /src
ADD https://codeload.github.com/ollama/ollama/tar.gz/02480ca2a47153e1f9c31cbe1e05536da97ce1ba /tmp/source.tar.gz
RUN echo 'b9f5996f04445bee1509f6c08e827142d9e334dc9061b3642fd6c7705d71f5fa  /tmp/source.tar.gz' | sha256sum -c - && tar -xzf /tmp/source.tar.gz --strip-components=1
COPY deploy/secure/ollama.go.mod ./go.mod
COPY deploy/secure/ollama.go.sum ./go.sum
RUN CGO_ENABLED=1 go build -mod=readonly -trimpath -buildmode=pie -ldflags='-X github.com/ollama/ollama/version.Version=0.40.15' -o /ollama .
FROM ollama/ollama:0.40.15@sha256:0e59999e0e8f9fd4e704bd788a89b7e4cad399367fb1365f8c102ac662288761
# Retain every upstream native CPU/GPU backend, model mount and environment.
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY --from=build --chmod=0755 /ollama /usr/bin/ollama
