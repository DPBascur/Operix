FROM node:24.2.0-bookworm-slim AS build
WORKDIR /app
RUN npm install --global pnpm@11.28.2
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend ./
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:18000/api/v1
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL NEXT_PUBLIC_DATA_SOURCE=api NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:24.2.0-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
COPY LICENSE THIRD_PARTY_NOTICES.md ./
USER node
EXPOSE 3000
CMD ["node", "server.js"]
