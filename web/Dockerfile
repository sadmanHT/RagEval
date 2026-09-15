FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund

FROM node:24-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run typecheck && npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

RUN addgroup --system --gid 10001 rageval \
    && adduser --system --uid 10001 --ingroup rageval rageval

COPY --from=builder --chown=rageval:rageval /app/.next/standalone ./
COPY --from=builder --chown=rageval:rageval /app/.next/static ./.next/static

USER rageval
EXPOSE 3000
CMD ["node", "server.js"]
