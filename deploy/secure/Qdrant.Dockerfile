FROM node:24.22.2-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS npm-tool
WORKDIR /opt/npm
RUN apk upgrade --no-cache
ADD https://registry.npmjs.org/npm/-/npm-12.2.2.tgz /tmp/npm.tgz
RUN echo '2a09606d9c9a71fee31fe147b8d46a56e0b3422f15848d9aec9f3b231e3716c3d3b99a065a62175c6759b4150e03bf6fc0bf8825112a511573ba903b3ec41370  /tmp/npm.tgz' | sha512sum -c - \
    && tar -xzf /tmp/npm.tgz --strip-components=1 \
    && rm /tmp/npm.tgz \
    && rm -rf /usr/local/lib/node_modules/npm /opt/yarn* \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/yarn /usr/local/bin/yarnpkg
COPY web/build-tools/npm.package.json ./package.json
COPY web/build-tools/npm.package-lock.json ./package-lock.json
RUN node bin/npm-cli.js ci --omit=dev --ignore-scripts \
    && ln -s /opt/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /opt/npm/bin/npx-cli.js /usr/local/bin/npx

FROM npm-tool AS dashboard
WORKDIR /ui
RUN apk add --no-cache git
ADD https://codeload.github.com/qdrant/qdrant-web-ui/tar.gz/90a83dd67bb9e3f84cf62daed14a9489ae1e7fdd /tmp/ui.tar.gz
RUN echo '5f0375093d04998456536f123882cfab67ed9ef0227c9761a046a82b45fcfb55  /tmp/ui.tar.gz' | sha256sum -c - && tar -xzf /tmp/ui.tar.gz --strip-components=1
COPY deploy/secure/dashboard.package.json ./package.json
COPY deploy/secure/dashboard.package-lock.json ./package-lock.json
RUN npm ci && npm audit && npm run build-qdrant

FROM rust:1.98.1-bookworm@sha256:93ce27a88655056a51dbdd8f5f2d7ddc071c7b0070fb288a37b5a285fc83971e AS build
WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends clang lld cmake protobuf-compiler libprotobuf-dev libunwind-dev liblzma-dev && rm -rf /var/lib/apt/lists/*
ADD https://codeload.github.com/qdrant/qdrant/tar.gz/222b2e44ab1c3f17e8246396ead6558e45041df7 /tmp/source.tar.gz
RUN echo 'd7d6c5b6197b63b24a89c753bb8ff2e3c9a67e5186087c2018c280b9d0398d80  /tmp/source.tar.gz' | sha256sum -c - && tar -xzf /tmp/source.tar.gz --strip-components=1
COPY deploy/secure/qdrant.Cargo.lock ./Cargo.lock
ENV CARGO_BUILD_JOBS=2
RUN test -f /usr/include/google/protobuf/timestamp.proto && cargo rustc --locked --release --features=stacktrace --bin qdrant -- -C link-arg=-llzma -C link-arg=-Wl,--push-state,--no-as-needed -C link-arg=-lgcc_s -C link-arg=-Wl,--pop-state
RUN readelf -dW target/release/qdrant | grep 'Shared library: \[libgcc_s.so.1\]'
RUN cargo install --locked cargo-sbom --version 0.10.0 && cargo sbom > /qdrant.spdx.json

FROM qdrant/qdrant:v1.20.0@sha256:9bfc89f9914fc14876a88c05270685921a55b8877b254a98bcc1cc2f0a424cd2 AS upstream
FROM cgr.dev/chainguard/wolfi-base@sha256:8509ee4351a2e501b7f98201f2e2642396e82020c61a589cacdcfe74b9de46c1
RUN apk add --no-cache bash=5.3-r14 libstdc++=16.2.0-r2 libunwind=1.8.3-r7 xz=5.8.4-r1 tzdata=2026f-r0
COPY --from=upstream /qdrant/config /qdrant/config
COPY --from=upstream /qdrant/entrypoint.sh /qdrant/entrypoint.sh
COPY --from=build /src/target/release/qdrant /qdrant/qdrant
COPY --from=build /qdrant.spdx.json /qdrant/qdrant.spdx.json
COPY --from=dashboard /ui/dist /qdrant/static
WORKDIR /qdrant
USER 0:0
ENV TZ=Etc/UTC RUN_MODE=production
EXPOSE 6333 6334
CMD ["./entrypoint.sh"]
