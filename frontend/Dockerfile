FROM node:24-alpine

WORKDIR /app/frontend

ARG NEXT_PUBLIC_API_URL=http://localhost:8058
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]

