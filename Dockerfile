# ===== 阶段 1：构建前端 =====
FROM node:20-alpine AS fe-build

WORKDIR /fe
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ===== 阶段 2：准备后端依赖 =====
FROM python:3.13-slim AS backend-deps

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt supervisor

# ===== 阶段 3：运行时（Nginx + uvicorn 一个容器） =====
FROM backend-deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DEBUG=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx tzdata curl \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/*

COPY backend/ /app/backend/
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY supervisord.conf /etc/supervisord.conf
COPY --from=fe-build /fe/dist /app/frontend/dist

RUN mkdir -p /app/backend/data/kline_cache /app/backend/data/replay_reports /app/backend/data/logs

WORKDIR /app/backend

EXPOSE 80 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1:80/api/v1/system/health || exit 1

CMD ["supervisord", "-c", "/etc/supervisord.conf"]