# Triển khai lên Amazon EKS (RDS + EBS, chạy HTTP)

```
Internet ──HTTP──► ALB (Ingress greenmart-alb) ─► Service gateway ─► gateway nginx ─► web / user / catalog …
                                                               │             catalog-service ─► EBS gp3 (PVC greenmart-media, ảnh sản phẩm)
                                          5 service ─► RDS MySQL 8.0  (tạo bằng Terraform)
```
Chưa có: Route 53, TLS/ACM (sẽ thêm sau). Truy cập bằng DNS của load balancer qua **HTTP**.

> **Đã kiểm chứng:** `kustomize build` + kubeconform (schema K8s 1.30) cho overlay. **Chưa chạy trên AWS thật** – thử ở môi trường thử trước.

## 1. Hạ tầng bằng Terraform
Làm theo `infra/terraform/README.md` (RDS + addon EBS CSI + snapshot EBS + secret + 5 database). Sau `terraform apply` ghi lại `rds_address` và `rds_master_secret_arn`.

## 1b. Cài AWS Load Balancer Controller (bắt buộc cho ALB)
```bash
CLUSTER_NAME=greenmart AWS_REGION=ap-southeast-1 INSTALL_TOOLS=true DEPLOY_SAMPLE=false bash infra/eks-bootstrap/bootstrap.sh
```
`DEPLOY_SAMPLE=false` để không tạo thêm ALB cho app mẫu 2048 (tốn tiền). Subnet public của VPC cần tag `kubernetes.io/role/elb=1` (eksctl tự gắn).

## 2. Image lên ECR (mỗi service một repository)
```bash
ACCOUNT_ID=111122223333 AWS_REGION=ap-southeast-1 TAG=1.0.0 bash k8s/overlays/eks/push-images.sh   # ở thư mục gốc dự án
```

## 3. Sửa overlay
`k8s/overlays/eks/kustomization.yaml`: đổi account id/tag của `images:` và `DB_HOST` = `rds_address`.

## 4. Triển khai (secret + 5 database do Terraform lo)
`terraform apply` ở bước 1 đã: tự sinh mọi secret, tạo namespace `greenmart` + Secret `greenmart-secrets`, và chạy Job tạo
5 database + 5 user trên RDS (đợi xong mới kết thúc). Không phải gõ secret bằng tay.
```bash
kubectl apply -k k8s/overlays/eks
kubectl -n greenmart wait --for=condition=complete job -l app.kubernetes.io/component=migrate --timeout=300s
kubectl -n greenmart rollout status deploy/web deploy/gateway
kubectl -n greenmart get ingress greenmart-alb -w   # cột ADDRESS = DNS của ALB (vài phút mới có)
```
Cần AWS CLI trên máy chạy Terraform (provider kubernetes dùng `aws eks get-token`).

## 5. Điền DNS của load balancer
Link trong email đặt lại mật khẩu dùng `PUBLIC_HOST`. Khi đã có DNS của ALB, sửa trong `kustomization.yaml` (patch ConfigMap):
`PUBLIC_HOST: <dns>`, `CSRF_TRUSTED_ORIGINS: http://<dns>`; rồi:
```bash
kubectl apply -k k8s/overlays/eks
kubectl -n greenmart rollout restart deploy/user-service deploy/web
```

## 6. Sau lần đầu
```bash
# ảnh sản phẩm cũ vào volume EBS
POD=$(kubectl -n greenmart get pod -l app.kubernetes.io/name=catalog-service -o name | head -1)
kubectl -n greenmart cp media/products ${POD#pod/}:/media/products
# tài khoản Django admin
kubectl -n greenmart exec -it deploy/user-service    -- python manage.py createsuperuser
kubectl -n greenmart exec -it deploy/catalog-service -- python manage.py createsuperuser
```
Chuyển dữ liệu `db.sqlite3` cũ: mục 4 của `k8s/README.md`, nhưng trong `k8s/jobs/data-migrator.yaml` đổi `MYSQL_USER` từ `root` thành `admin` và image sang ECR.

## 7. Kiểm tra
```bash
curl -i http://<dns-ALB>/gateway-health          # 200 ok
BASE=http://<dns-ALB> ADMIN_USER=<staff> ADMIN_PASSWORD=<mk> python tests/e2e_smoke.py
```
Thử upload ảnh sản phẩm ở admin: ảnh phải hiện ở trang chủ (kiểm tra EBS + proxy `/media/`).

## Điểm cần biết
- **Chỉ HTTP**: mật khẩu và cookie đăng nhập đi không mã hóa. Chỉ dùng thử/nội bộ; hạn chế nguồn truy cập bằng annotation `alb.ingress.kubernetes.io/inbound-cidrs` trong `ingress-alb.yaml` (đang để `0.0.0.0/0` – thay bằng IP của bạn). Thêm Route 53 + ACM để có TLS ở bước sau.
- **EBS chỉ gắn được 1 pod ở 1 AZ**: `catalog-service` chạy 1 replica, cập nhật kiểu `Recreate` (gián đoạn ngắn khi deploy); pod bị ghim theo AZ của volume. Ảnh được `catalog-service` phục vụ qua `/media/` (đủ cho quy mô nhỏ).
- Snapshot EBS hằng ngày do Terraform (DLM) lo; RDS có backup tự động. StorageClass `Retain` – xóa PVC không xóa volume.
- Không có `networkpolicy` hạn chế nguồn vào gateway (đã mở `0.0.0.0/0`); các policy giữa service vẫn giữ.
- Image chạy bằng root; Secret tạo bằng `kubectl` – production nên dùng External Secrets + Secrets Manager.
- Lỗi thường gặp: PVC `Pending` → addon `aws-ebs-csi-driver` chưa chạy (xem `kubectl -n kube-system get pods | grep ebs`); `terraform apply` kẹt ở Job `rds-init` → xem `kubectl -n greenmart logs job/rds-init` (security group RDS, node chưa sẵn sàng); đăng nhập 403 CSRF → bước 5.
