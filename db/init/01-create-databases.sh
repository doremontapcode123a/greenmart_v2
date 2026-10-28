#!/bin/sh
# Chạy một lần khi volume MySQL còn trống. Mỗi service có database + tài khoản riêng, chỉ có quyền trên DB của mình.
set -e
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE DATABASE user_db      CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE catalog_db   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE order_db     CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE promotion_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE web_db       CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'user_svc'@'%'      IDENTIFIED WITH mysql_native_password BY '${USER_DB_PASSWORD}';
CREATE USER 'catalog_svc'@'%'   IDENTIFIED WITH mysql_native_password BY '${CATALOG_DB_PASSWORD}';
CREATE USER 'order_svc'@'%'     IDENTIFIED WITH mysql_native_password BY '${ORDER_DB_PASSWORD}';
CREATE USER 'promotion_svc'@'%' IDENTIFIED WITH mysql_native_password BY '${PROMOTION_DB_PASSWORD}';
CREATE USER 'web_svc'@'%'       IDENTIFIED WITH mysql_native_password BY '${WEB_DB_PASSWORD}';

GRANT ALL PRIVILEGES ON user_db.*      TO 'user_svc'@'%';
GRANT ALL PRIVILEGES ON catalog_db.*   TO 'catalog_svc'@'%';
GRANT ALL PRIVILEGES ON order_db.*     TO 'order_svc'@'%';
GRANT ALL PRIVILEGES ON promotion_db.* TO 'promotion_svc'@'%';
GRANT ALL PRIVILEGES ON web_db.*       TO 'web_svc'@'%';
FLUSH PRIVILEGES;
SQL
