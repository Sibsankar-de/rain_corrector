# syntax=docker/dockerfile:1
# Multi-stage so the runtime image carries no dev dependencies.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# -D skips the interactive password prompt, which would hang a non-interactive build.
RUN addgroup -g 10001 corrector \
    && adduser -D -H -u 10001 -G corrector -s /bin/sh corrector

# `output: "standalone"` emits a self-contained server; `next start` refuses to
# run against it, so the standalone entrypoint is what actually serves.
COPY --from=builder --chown=corrector:corrector /app/.next/standalone ./
COPY --from=builder --chown=corrector:corrector /app/.next/static ./.next/static
COPY --from=builder --chown=corrector:corrector /app/public ./public

USER corrector
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -qO- http://localhost:3000/ >/dev/null || exit 1

CMD ["node", "server.js"]
