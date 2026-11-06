FROM node:24-bookworm-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9 AS dashboard
WORKDIR /ui
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git && rm -rf /var/lib/apt/lists/*
ADD https://codeload.github.com/qdrant/qdrant-web-ui/tar.gz/90a83dd67bb9e3f84cf62daed14a9489ae1e7fdd /tmp/ui.tar.gz
RUN echo '5f0375093d04998456536f123882cfab67ed9ef0227c9761a046a82b45fcfb55  /tmp/ui.tar.gz' | sha256sum -c - && tar -xzf /tmp/ui.tar.gz --strip-components=1
COPY deploy/secure/dashboard.package.json ./package.json
COPY deploy/secure/dashboard.package-lock.json ./package-lock.json
RUN npm ci && npm audit && npm run build-qdrant

FROM rust:1.98.1-bookworm@sha256:93ce27a88655056a51dbdd8f5f2d7ddc071c7b0070fb288a37b5a285fc83971e AS build
WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends clang lld cmake protobuf-compiler libprotobuf-dev libunwind-dev && rm -rf /var/lib/apt/lists/*
ADD https://codeload.github.com/qdrant/qdrant/tar.gz/222b2e44ab1c3f17e8246396ead6558e45041df7 /tmp/source.tar.gz
RUN echo 'd7d6c5b6197b63b24a89c753bb8ff2e3c9a67e5186087c2018c280b9d0398d80  /tmp/source.tar.gz' | sha256sum -c - && tar -xzf /tmp/source.tar.gz --strip-components=1
COPY deploy/secure/qdrant.Cargo.lock ./Cargo.lock
ENV CARGO_BUILD_JOBS=2
RUN test -f /usr/include/google/protobuf/timestamp.proto && cargo build --locked --release --features=stacktrace --bin qdrant
RUN cargo install --locked cargo-sbom --version 0.10.0 && cargo sbom > /qdrant.spdx.json

FROM qdrant/qdrant:v1.20.0@sha256:9bfc89f9914fc14876a88c05270685921a55b8877b254a98bcc1cc2f0a424cd2
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/target/release/qdrant /qdrant/qdrant
COPY --from=build /qdrant.spdx.json /qdrant/qdrant.spdx.json
COPY --from=dashboard /ui/dist /qdrant/static
