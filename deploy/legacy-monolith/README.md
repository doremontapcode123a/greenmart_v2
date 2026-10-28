# CI/CD của bản monolith (chưa chuyển đổi)

Các file ở đây (Jenkinsfile, taskdef-template.json, workflow GitHub Actions -> thư mục `github-workflows`, Dockerfile/compose cũ)
build và deploy **một image `greenmart-app` + `greenmart-nginx`** lên ECS. Chúng không còn đúng với kiến trúc 5 service + gateway,
nên được để riêng ở đây, KHÔNG nằm trong `.github/` (để không chạy nhầm khi push).

Việc cần làm khi lên môi trường thật: mỗi service (user, catalog, order, promotion, web, gateway) cần một repo ECR / image riêng,
task definition ECS (hoặc service riêng), và MySQL dùng RDS thay cho container `mysql` trong docker-compose.
