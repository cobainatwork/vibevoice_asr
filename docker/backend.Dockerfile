FROM python:3.11-slim

# 系統依賴：ffmpeg + Docker CLI（backend 控制其他 container 用）
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安裝 Python 依賴
# 內測階段：包 dev deps（pytest / ruff / mypy）方便容器內跑單測。
# 進入正式部署前可改 multi-stage 區分 prod / dev。
# `poetry install` 失敗時 fallback 跑 lock --no-update：開發期改 pyproject 但忘了
# 在 host 端 lock 時不擋 build；commit lock file 前 image 會自動 catch up。
COPY backend/pyproject.toml backend/poetry.lock* ./
RUN pip install --no-cache-dir poetry==1.8.3 \
    && poetry config virtualenvs.create false \
    && (poetry install --no-root || (poetry lock --no-update && poetry install --no-root))

# 複製應用程式碼
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/templates ./templates
COPY backend/tests ./tests
COPY backend/alembic.ini ./

# 建立 data 目錄掛載點
RUN mkdir -p /data

EXPOSE 8080

# 預設給 backend；worker 在 docker-compose 用 command override
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
