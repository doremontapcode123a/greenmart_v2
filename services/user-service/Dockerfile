# Build context = thư mục gốc dự án (docker compose đã cấu hình): docker build -f services/user-service/Dockerfile .
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/common \
    WSGI_MODULE=user_service

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev pkg-config \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/services/user-service
COPY common/greenmart_common/requirements.txt /app/common/greenmart_common/requirements.txt
COPY services/user-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY common /app/common
COPY services/user-service /app/services/user-service
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
