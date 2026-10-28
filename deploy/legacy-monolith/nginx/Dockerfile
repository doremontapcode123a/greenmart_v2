FROM nginx:alpine

# Xóa cấu hình default của Nginx (nếu cần thiết để tránh xung đột)
RUN rm /etc/nginx/conf.d/default.conf

# Copy file cấu hình nginx của bạn vào
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Copy trực tiếp các thư mục chứa file tĩnh từ project gốc vào image của Nginx
# COPY staticfiles /staticfiles
COPY media /media