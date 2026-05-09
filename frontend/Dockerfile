# Stage 1: Dependencies
FROM node:24-alpine AS deps

# CN mirror support — pass via --build-arg or docker compose .env
ARG NPM_REGISTRY
ARG ALPINE_MIRROR

WORKDIR /app
COPY package.json package-lock.json ./
# hadolint ignore=SC2086
RUN if [ -n "$ALPINE_MIRROR" ]; then \
      sed -i "s|dl-cdn.alpinelinux.org|${ALPINE_MIRROR}|g" /etc/apk/repositories; \
    fi && \
    if [ -n "$NPM_REGISTRY" ]; then npm config set registry "$NPM_REGISTRY"; fi && \
    npm ci

# Stage 2: Build
FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Stage 3: Production
FROM node:24-alpine AS runner

ARG ALPINE_MIRROR

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# hadolint ignore=SC2086
RUN if [ -n "$ALPINE_MIRROR" ]; then \
      sed -i "s|dl-cdn.alpinelinux.org|${ALPINE_MIRROR}|g" /etc/apk/repositories; \
    fi && \
    addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs && \
    mkdir -p /app/data && \
    chown nextjs:nodejs /app/data
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
