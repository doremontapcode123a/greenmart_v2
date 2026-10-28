#!/bin/sh
set -e

echo "Đang tự động chạy Database Migrations..."
python manage.py migrate --noinput

echo "Khởi động Server..."

exec "$@"