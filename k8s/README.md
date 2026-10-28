# Triển khai trên Kubernetes

Kustomize, namespace `greenmart`. Base ở `k8s/base/`; **EKS**: dùng overlay `k8s/overlays/eks/` (xem `k8s/overlays/eks/README.md`). Cùng kiến trúc với docker-compose: MySQL → 4 service domain + web → gateway nginx → Ingress.

| File (trong `base/`) | Nội dung |
|---|---|
| `namespace.yaml`, `configmap.yaml` | Namespace; cấu hình chung (**đổi domain** ở đây) |
| `../secrets.example.yaml` | Mẫu Secret – **không** nằm trong kustomization, tạo Secret bằng lệnh bên dưới |
| `mysql.yaml` | MySQL 8 StatefulSet 10Gi + script tạo 5 DB/5 user (dev/staging; production nên dùng RDS/Cloud SQL) |
| `user-/catalog-/order-/promotion-service.yaml`, `web.yaml` | Deployment + Service (ClusterIP :8000) |
| `migrate-jobs.yaml` | 5 Job `migrate` – mỗi service migrate DB của chính nó |
| `gateway.yaml` | nginx (ConfigMap) + 3 initContainer gom static của web/user/catalog vào `emptyDir` |
| `media-pvc.yaml` | PVC **ReadWriteMany** cho ảnh sản phẩm (catalog ghi, gateway đọc) |
| `ingress.yaml`, `hpa.yaml`, `networkpolicy.yaml` | Ingress (nginx) · autoscale web/catalog/order · chỉ cho phép đúng luồng gọi giữa các pod |
| `../jobs/` | Chuyển dữ liệu từ `db.sqlite3` cũ (thủ công, xem bên dưới) |

## 1. Build & push image (chạy ở thư mục gốc dự án)

```bash
REG=registry.example.com/greenmart      # registry của bạn
for s in user-service catalog-service order-service promotion-service; do
  docker build -f services/$s/Dockerfile -t $REG/$s:1.0.0 . && docker push $REG/$s:1.0.0
done
docker build -f web/Dockerfile -t $REG/web:1.0.0 . && docker push $REG/web:1.0.0
```
Sửa `images:` trong `k8s/base/kustomization.yaml` cho khớp `$REG` và tag.

## 2. Cấu hình

- `base/configmap.yaml`: `PUBLIC_HOST`, `CSRF_TRUSTED_ORIGINS`, `WEB_ALLOWED_HOSTS`, cấu hình email. `base/ingress.yaml`: host + TLS secret.
- Tạo Secret (giá trị ngẫu nhiên, không lưu vào git):

```bash
kubectl apply -f k8s/base/namespace.yaml
r() { python3 -c "import secrets; print(secrets.token_urlsafe(32))"; }
kubectl -n greenmart create secret generic greenmart-secrets \
  --from-literal=SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(60))')" \
  --from-literal=INTERNAL_API_TOKEN="$(r)" \
  --from-literal=MYSQL_ROOT_PASSWORD="$(r)" \
  --from-literal=USER_DB_PASSWORD="$(r)" --from-literal=CATALOG_DB_PASSWORD="$(r)" \
  --from-literal=ORDER_DB_PASSWORD="$(r)" --from-literal=PROMOTION_DB_PASSWORD="$(r)" \
  --from-literal=WEB_DB_PASSWORD="$(r)" --from-literal=EMAIL_HOST_PASSWORD=""
```
  (Dùng Sealed Secrets / External Secrets nếu cluster có.) `INTERNAL_API_TOKEN` phải giống nhau ở mọi service – chỉ cần một Secret nên luôn đúng.

## 3. Triển khai

```bash
kubectl apply -k k8s/base
kubectl -n greenmart wait --for=condition=complete job -l app.kubernetes.io/component=migrate --timeout=300s
kubectl -n greenmart rollout status deploy/web deploy/gateway
```
Nếu Job `migrate-*` của lần trước còn tồn tại và bạn đổi image: `kubectl -n greenmart delete job -l app.kubernetes.io/component=migrate` rồi apply lại.

Sau lần đầu:
```bash
# Ảnh sản phẩm cũ vào PVC media
POD=$(kubectl -n greenmart get pod -l app.kubernetes.io/name=catalog-service -o name | head -1)
kubectl -n greenmart cp media/products ${POD#pod/}:/media/products
# Tài khoản cho Django admin (/admin/ và /admin/catalog/)
kubectl -n greenmart exec -it deploy/user-service    -- python manage.py createsuperuser
kubectl -n greenmart exec -it deploy/catalog-service -- python manage.py createsuperuser
```
Kiểm tra nhanh không cần DNS: `kubectl -n greenmart port-forward svc/gateway 8088:80` rồi `BASE=http://localhost:8088 python tests/e2e_smoke.py`
(qua port-forward không có TLS nên cần `PUBLIC_SCHEME=http` và CSRF origin `http://localhost:8088` trong configmap, hoặc test qua Ingress thật).

## 4. Chuyển dữ liệu từ db.sqlite3 cũ (một lần)

```bash
docker build -f scripts/Dockerfile -t $REG/data-migrator:1.0.0 . && docker push $REG/data-migrator:1.0.0
# sửa image trong k8s/jobs/data-migrator.yaml (host/user/password đã lấy từ ConfigMap/Secret)
kubectl -n greenmart apply -f k8s/jobs/legacy-data.yaml
kubectl -n greenmart wait --for=condition=Ready pod/legacy-uploader
kubectl -n greenmart cp /đường/dẫn/db.sqlite3 legacy-uploader:/legacy/db.sqlite3
kubectl -n greenmart delete pod legacy-uploader
kubectl -n greenmart apply -f k8s/jobs/data-migrator.yaml && kubectl -n greenmart logs -f job/data-migrator   # --dry-run: chỉ thống kê
# hài lòng thì xóa "--dry-run" trong jobs/data-migrator.yaml (thêm "--truncate" nếu cần ghi đè), delete job, apply lại
```

## Lưu ý

- **Đã kiểm chứng**: `kustomize build` thành công và 38 object hợp lệ với schema Kubernetes 1.30 (kubeconform, strict). **Chưa chạy trên cluster thật** – nên thử ở staging trước.
- **Storage RWX là yêu cầu cứng** cho media (NFS/EFS/Filestore/CephFS…). Nếu cluster chỉ có RWO: để `catalog-service` 1 replica, chuyển nginx media sang sidecar cùng pod, hoặc đưa ảnh lên object storage (cần sửa code catalog).
- Mỗi replica của gateway tự gom static khi khởi động (initContainer) – không cần volume dùng chung, nhưng pod khởi động lâu hơn vài giây.
- Deployment đặt `RUN_MIGRATE=0`; migrate chạy bằng Job để tránh nhiều replica migrate cùng lúc. Nhớ chờ Job xong trước khi dùng.
- Liveness probe chỉ kiểm tra TCP; readiness gọi `/health/` (có kiểm tra DB). Probe của `web` gửi `Host: localhost` vì `ALLOWED_HOSTS` của web không chứa IP pod.
- Image hiện chạy bằng root (Dockerfile chưa có `USER`); manifest đã `drop ALL` capability trừ vài quyền cần thiết và tắt privilege escalation. Muốn chạy non-root cần thêm user vào Dockerfile và `fsGroup` cho PVC media.
- MySQL StatefulSet 1 replica không có HA/backup. Production: dùng DB managed, bỏ `mysql.yaml`, đặt `DB_HOST` trong configmap và tạo sẵn 5 DB/5 user theo script trong `mysql.yaml`.
- `networkpolicy.yaml` giả định Ingress Controller ở namespace `ingress-nginx` và CNI hỗ trợ NetworkPolicy.
- nginx trong `gateway.yaml` là bản sao của `gateway/nginx.conf` – sửa cấu hình thì sửa cả hai.
