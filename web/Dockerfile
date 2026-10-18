# Console dev server for docker compose (`make full-up`).
#
#   docker compose up -d   →  falkordb :6379 · api :8000 · web :5173
#
# Console on 5173, proxying /api to the api service. Production-ish
# single-server path: build once (`npm run build`) and let the API serve
# web/dist — see deploy/Dockerfile.
FROM node:24-bookworm-slim
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/index.html web/vite.config.js ./
COPY web/src ./src
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
