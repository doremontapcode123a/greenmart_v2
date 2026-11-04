#!/bin/sh
# Entrypoint dùng chung cho mọi service Django.
#   RUN_MIGRATE=1        chạy migrate khi khởi động (mỗi service chỉ migrate DB của chính nó)
#   RUN_COLLECTSTATIC=1  gom static vào volume dùng chung cho gateway
#   DJANGO_SUPERUSER_*   nếu có, tạo superuser cho Django admin (service có admin)
set -e

if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
  rm -rf "$PROMETHEUS_MULTIPROC_DIR"; mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
fi

if [ "${RUN_MIGRATE:-1}" = "1" ]; then
  echo "[entrypoint] migrate..."
  n=0
  until python manage.py migrate --noinput; do
    n=$((n+1))
    [ "$n" -ge 20 ] && { echo "[entrypoint] migrate thất bại sau $n lần"; exit 1; }
    echo "[entrypoint] DB chưa sẵn sàng, thử lại sau 3s ($n)"; sleep 3
  done
fi

if [ "${RUN_COLLECTSTATIC:-0}" = "1" ]; then
  python manage.py collectstatic --noinput >/dev/null
fi

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ] && [ "${CREATE_SUPERUSER:-0}" = "1" ]; then
  python manage.py createsuperuser --noinput 2>/dev/null || echo "[entrypoint] superuser đã tồn tại (bỏ qua)"
fi

exec gunicorn "${WSGI_MODULE}.wsgi:application" --bind 0.0.0.0:8000 \
  --workers "${WEB_CONCURRENCY:-2}" --access-logfile - --error-logfile -