FROM node:24.22.2-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS npm-tool
WORKDIR /opt/npm
RUN apk upgrade --no-cache
ADD https://registry.npmjs.org/npm/-/npm-12.2.2.tgz /tmp/npm.tgz
RUN echo '2a09606d9c9a71fee31fe147b8d46a56e0b3422f15848d9aec9f3b231e3716c3d3b99a065a62175c6759b4150e03bf6fc0bf8825112a511573ba903b3ec41370  /tmp/npm.tgz' | sha512sum -c - \
    && tar -xzf /tmp/npm.tgz --strip-components=1 \
    && rm /tmp/npm.tgz \
    && rm -rf /usr/local/lib/node_modules/npm /opt/yarn* \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/yarn /usr/local/bin/yarnpkg
COPY build-tools/npm.package.json ./package.json
COPY build-tools/npm.package-lock.json ./package-lock.json
RUN node bin/npm-cli.js ci --omit=dev --ignore-scripts \
    && ln -s /opt/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /opt/npm/bin/npx-cli.js /usr/local/bin/npx

FROM npm-tool AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN node /opt/npm/bin/npm-cli.js ci

FROM npm-tool AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN node /opt/npm/bin/npm-cli.js run build

FROM node:24.22.2-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS runtime
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
# The standalone server uses node directly; package managers are build tools.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm /opt/yarn* \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/yarn /usr/local/bin/yarnpkg \
    && addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
