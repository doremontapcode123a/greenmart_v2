FROM python:3.12-slim
RUN pip install --no-cache-dir pymysql cryptography
WORKDIR /scripts
COPY scripts/migrate_sqlite_to_mysql.py .
