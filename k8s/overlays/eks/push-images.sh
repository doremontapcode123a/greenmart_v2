#!/usr/bin/env bash
# Build & push 5 image lên ECR (tự tạo repository nếu chưa có). Chạy ở THƯ MỤC GỐC dự án.
#   ACCOUNT_ID=111122223333 AWS_REGION=ap-southeast-1 TAG=1.0.0 bash k8s/overlays/eks/push-images.sh
# Mỗi service một repository ECR riêng. Tiền tố tên repo mặc định "greenmart/" (-> greenmart/user-service);
# đặt REPO_PREFIX=greenmart- để có tên phẳng (-> greenmart-user-service). Phải khớp newName trong overlays/eks/kustomization.yaml.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash trên Windows: không tự đổi đường dẫn
: "${ACCOUNT_ID:?đặt ACCOUNT_ID}"; AWS_REGION="${AWS_REGION:-ap-southeast-1}"; TAG="${TAG:-1.0.0}"; REPO_PREFIX="${REPO_PREFIX:-greenmart/}"
REG="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REG"

build_push() {  # name dockerfile
  aws ecr describe-repositories --repository-names "${REPO_PREFIX}$1" --region "$AWS_REGION" >/dev/null 2>&1 \
    || aws ecr create-repository --repository-name "${REPO_PREFIX}$1" --region "$AWS_REGION" \
         --image-scanning-configuration scanOnPush=true >/dev/null
  docker build --platform linux/amd64 -f "$2" -t "$REG/${REPO_PREFIX}$1:$TAG" .
  docker push "$REG/${REPO_PREFIX}$1:$TAG"
}
for s in user-service catalog-service order-service promotion-service; do build_push "$s" "services/$s/Dockerfile"; done
build_push web web/Dockerfile
build_push data-migrator scripts/Dockerfile   # dùng cho bước chuyển dữ liệu cũ
echo "Xong. Image: $REG/${REPO_PREFIX}<service>:$TAG"
