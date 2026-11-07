FROM golang:1.27.3-bookworm@sha256:dc0963f32053e4bc451d24d87e3892d42d01021b61f093e98eb95c0352bb84b0 AS build
WORKDIR /src
ADD https://codeload.github.com/ollama/ollama/tar.gz/02480ca2a47153e1f9c31cbe1e05536da97ce1ba /tmp/source.tar.gz
RUN echo 'b9f5996f04445bee1509f6c08e827142d9e334dc9061b3642fd6c7705d71f5fa  /tmp/source.tar.gz' | sha256sum -c - && tar -xzf /tmp/source.tar.gz --strip-components=1
COPY deploy/secure/ollama.go.mod ./go.mod
COPY deploy/secure/ollama.go.sum ./go.sum
RUN CGO_ENABLED=1 go build -mod=readonly -trimpath -buildmode=pie -ldflags='-X github.com/ollama/ollama/version.Version=0.40.15' -o /ollama .
FROM ollama/ollama:0.40.15@sha256:0e59999e0e8f9fd4e704bd788a89b7e4cad399367fb1365f8c102ac662288761 AS upstream
FROM cgr.dev/chainguard/wolfi-base@sha256:8509ee4351a2e501b7f98201f2e2642396e82020c61a589cacdcfe74b9de46c1
RUN apk add --no-cache libstdc++=16.2.0-r2 libgomp=16.2.0-r2 libopenblas-0=0.3.34-r2 vulkan-loader-libs=1.4.368-r0
# Preserve the complete upstream native backend tree, including CUDA/JIT headers.
COPY --from=upstream /usr/lib/ollama /usr/lib/ollama
COPY --from=build --chmod=0755 /ollama /usr/bin/ollama
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV NVIDIA_VISIBLE_DEVICES=all
ENV OLLAMA_HOST=0.0.0.0:11434
EXPOSE 11434
ENTRYPOINT ["/bin/ollama"]
CMD ["serve"]
