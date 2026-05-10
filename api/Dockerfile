FROM python:3.12-slim

# プロキシ環境向け build args (.env で HTTP_PROXY 等を設定すると docker-compose 経由で渡る)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

WORKDIR /app

# OS パッケージ (curl は HEALTHCHECK / デバッグ用)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依存
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# アプリケーション
COPY app /app/app

EXPOSE 8000

# 開発時は --reload を付けたい場合は compose 側で command を上書き
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
