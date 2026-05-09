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
COPY backend/pyproject.toml backend/poetry.lock* ./
RUN pip install --no-cache-dir poetry==1.8.3 \
    && poetry config virtualenvs.create false \
    && poetry install --no-root --without dev

# 複製應用程式碼
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/templates ./templates
COPY backend/alembic.ini ./

# 建立 data 目錄掛載點
RUN mkdir -p /data

EXPOSE 8080

# 預設給 backend；worker 在 docker-compose 用 command override
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
