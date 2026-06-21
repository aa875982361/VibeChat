# syntax=docker/dockerfile:1.7

FROM node:24-alpine

WORKDIR /app/frontend

ARG NEXT_PUBLIC_API_URL=http://localhost:8058
ARG NPM_CONFIG_REGISTRY=https://registry.npmmirror.com
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --fund=false

COPY frontend ./
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
