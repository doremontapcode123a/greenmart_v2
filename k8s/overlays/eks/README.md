# Triển khai lên Amazon EKS

Kiến trúc trên AWS: **Route 53 → ALB (TLS bằng ACM) → gateway nginx → web/user/catalog…**, dữ liệu ở **RDS MySQL 8.0**, ảnh sản phẩm ở **EFS**, image ở **ECR**.
Overlay `k8s/overlays/eks` biến base thành cấu hình đó (bỏ MySQL container, StorageClass EFS, Ingress ALB, image ECR, job tạo DB trên RDS).

> **Đã kiểm chứng:** `kustomize build` + kubeconform (schema K8s 1.30) cho overlay. **Chưa chạy trên tài khoản AWS thật** – làm từng bước dưới đây ở môi trường thử trước.
> Các lệnh `eksctl`/`aws`/`helm` bên dưới là hướng dẫn chuẩn; tên policy/phiên bản addon có thể đổi, đối chiếu tài liệu AWS khi gặp lỗi.

Thay các giá trị mẫu: `ACCOUNT_ID=111122223333`, region `ap-southeast-1`, domain `shop.example.com`, tên cluster `greenmart`.

## 0. Cluster và các addon cần có

```bash
export AWS_REGION=ap-southeast-1 CLUSTER=greenmart ACCOUNT_ID=111122223333
eksctl create cluster --name $CLUSTER --region $AWS_REGION --managed --with-oidc \
  --nodegroup-name ng --node-type t3.medium --nodes 2 --nodes-min 2 --nodes-max 4
```

| Cần | Dùng để | Cài |
|---|---|---|
| **AWS Load Balancer Controller** | tạo ALB từ Ingress | Helm theo hướng dẫn AWS (tạo IAM policy + service account, `helm install aws-load-balancer-controller eks/aws-load-balancer-controller -n kube-system --set clusterName=$CLUSTER ...`) |
| **EFS CSI driver** | PVC ReadWriteMany cho ảnh | `eksctl create iamserviceaccount --cluster $CLUSTER --namespace kube-system --name efs-csi-controller-sa --attach-policy-arn arn:aws:iam::aws:policy/service-role/AmazonEFSCSIDriverPolicy --approve --role-only --role-name AmazonEKS_EFS_CSI_DriverRole` rồi `eksctl create addon --cluster $CLUSTER --name aws-efs-csi-driver --service-account-role-arn arn:aws:iam::$ACCOUNT_ID:role/AmazonEKS_EFS_CSI_DriverRole --force` |
| **metrics-server** | HPA | `eksctl create addon --cluster $CLUSTER --name metrics-server` |
| Network policy (tuỳ chọn) | `networkpolicy.yaml` | bật trong addon VPC CNI (`enableNetworkPolicy: "true"`) hoặc dùng Calico. Không bật thì policy bị bỏ qua (vẫn chạy được) |

## 1. Tài nguyên AWS (cùng VPC với cluster)

**EFS (ảnh sản phẩm)**
```bash
VPC=$(aws eks describe-cluster --name $CLUSTER --query cluster.resourcesVpcConfig.vpcId --output text)
CSG=$(aws eks describe-cluster --name $CLUSTER --query cluster.resourcesVpcConfig.clusterSecurityGroupId --output text)
EFSSG=$(aws ec2 create-security-group --group-name greenmart-efs --description "EFS greenmart" --vpc-id $VPC --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $EFSSG --protocol tcp --port 2049 --source-group $CSG
FS=$(aws efs create-file-system --encrypted --tags Key=Name,Value=greenmart-media --query FileSystemId --output text)
for S in $(aws eks describe-cluster --name $CLUSTER --query 'cluster.resourcesVpcConfig.subnetIds[]' --output text); do
  aws efs create-mount-target --file-system-id $FS --subnet-id $S --security-groups $EFSSG
done
echo $FS     # → điền vào overlays/eks/storageclass-efs.yaml (fileSystemId)
```

**RDS MySQL** – tạo trên Console hoặc CLI với các điều kiện bắt buộc:
- Engine **MySQL 8.0** (không chọn 8.4: `mysql_native_password` bị tắt mặc định, script tạo user sẽ lỗi).
- Cùng VPC, subnet group riêng (private), **Security Group cho phép 3306 từ `$CSG`** (SG của cluster/node).
- Master user (ví dụ `admin`) + mật khẩu mạnh; bật encryption, automated backup; production nên **Multi-AZ**.
- Ghi lại **endpoint** → điền `DB_HOST` trong `kustomization.yaml` của overlay.

**ACM**: xin certificate cho domain trong **cùng region** (DNS validation) → lấy ARN.

## 2. Push image lên ECR

```bash
ACCOUNT_ID=$ACCOUNT_ID AWS_REGION=$AWS_REGION TAG=1.0.0 bash k8s/overlays/eks/push-images.sh   # chạy ở thư mục gốc dự án
```
Script tự tạo repository `greenmart/<service>`, build `linux/amd64` và push (cả `data-migrator`). Node Graviton (arm64) thì đổi `--platform` trong script.
Node group của eksctl đã có quyền kéo image từ ECR cùng tài khoản.

## 3. Sửa overlay

Mở `k8s/overlays/eks/kustomization.yaml` và đổi mọi dòng có chữ **ĐỔI**: account id/tag của `images:`, `DB_HOST` (RDS endpoint), domain (4 chỗ), ACM ARN. Đổi `fileSystemId` trong `storageclass-efs.yaml`.

## 4. Secret rồi triển khai

```bash
kubectl apply -f k8s/base/namespace.yaml
r() { python3 -c "import secrets; print(secrets.token_urlsafe(32))"; }
kubectl -n greenmart create secret generic greenmart-secrets \
  --from-literal=SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(60))')" \
  --from-literal=INTERNAL_API_TOKEN="$(r)" \
  --from-literal=USER_DB_PASSWORD="$(r)" --from-literal=CATALOG_DB_PASSWORD="$(r)" \
  --from-literal=ORDER_DB_PASSWORD="$(r)" --from-literal=PROMOTION_DB_PASSWORD="$(r)" --from-literal=WEB_DB_PASSWORD="$(r)" \
  --from-literal=MYSQL_ROOT_PASSWORD="unused-on-rds" \
  --from-literal=RDS_ADMIN_USER=admin --from-literal=RDS_ADMIN_PASSWORD='<mật khẩu master RDS>' \
  --from-literal=EMAIL_HOST_PASSWORD=""

kubectl apply -k k8s/overlays/eks
kubectl -n greenmart wait --for=condition=complete job/rds-init --timeout=300s
kubectl -n greenmart wait --for=condition=complete job -l app.kubernetes.io/component=migrate --timeout=300s
kubectl -n greenmart rollout status deploy/web deploy/gateway
kubectl -n greenmart get ingress greenmart       # cột ADDRESS = DNS của ALB (có thể mất 2–3 phút)
```
Trỏ DNS: Route 53 → bản ghi **Alias A** của `shop.example.com` tới ALB đó.

> Production nên thay `kubectl create secret` bằng **External Secrets Operator + AWS Secrets Manager** (hoặc Sealed Secrets) để không để mật khẩu trong shell history.

## 5. Sau lần đầu

```bash
# ảnh sản phẩm cũ vào EFS
POD=$(kubectl -n greenmart get pod -l app.kubernetes.io/name=catalog-service -o name | head -1)
kubectl -n greenmart cp media/products ${POD#pod/}:/media/products
# tài khoản Django admin
kubectl -n greenmart exec -it deploy/user-service    -- python manage.py createsuperuser
kubectl -n greenmart exec -it deploy/catalog-service -- python manage.py createsuperuser
```

**Chuyển dữ liệu `db.sqlite3` cũ** – làm theo mục 4 của `k8s/README.md`, nhưng với RDS cần đổi trong `k8s/jobs/data-migrator.yaml`: image → ECR (`.../greenmart/data-migrator:1.0.0`), `MYSQL_USER` → `admin`, và key của `MYSQL_PASSWORD` → `RDS_ADMIN_PASSWORD`. Host tự lấy từ `DB_HOST` trong ConfigMap.

## 6. Kiểm tra

```bash
curl -I https://shop.example.com/gateway-health        # 200
BASE=https://shop.example.com ADMIN_USER=<staff> ADMIN_PASSWORD=<mk> python tests/e2e_smoke.py
```
Thử riêng: đăng nhập, thêm giỏ, upload ảnh sản phẩm ở admin (ảnh phải hiện trên trang chủ – kiểm tra EFS đã ghi/đọc đúng).

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân |
|---|---|
| PVC `greenmart-media` mãi `Pending` | chưa cài EFS CSI driver, sai `fileSystemId`, hoặc SG EFS chưa mở 2049 từ SG cluster |
| Ingress không có ADDRESS | chưa cài AWS Load Balancer Controller / thiếu tag subnet (`kubernetes.io/role/elb`) |
| Target group ALB `unhealthy` | health check phải là `/gateway-health` (đã cấu hình); kiểm tra NetworkPolicy chặn ALB |
| `rds-init` / `migrate-*` lỗi kết nối | SG của RDS chưa cho phép 3306 từ SG cluster; sai `DB_HOST` |
| `rds-init` lỗi `mysql_native_password` | RDS dùng MySQL 8.4 – chọn 8.0 |
| Đăng nhập/POST bị **403 CSRF** | `CSRF_TRUSTED_ORIGINS` phải đúng `https://<domain>`; truy cập bằng đúng domain đó |
| Web trả 400 *Invalid HTTP_HOST* | domain truy cập chưa có trong `WEB_ALLOWED_HOSTS` |

## Chi phí & bảo mật (cần biết)
- Chi phí chạy liên tục: EKS control plane + node + ALB + NAT + RDS + EFS. Dev thì dùng 1 node, RDS single-AZ và tắt khi không dùng.
- Đặt node và RDS ở **private subnet**; ALB ở public subnet. Cân nhắc AWS WAF gắn vào ALB.
- `0.0.0.0/0` trong NetworkPolicy gateway: siết lại thành CIDR VPC của bạn.
- Image chạy bằng root (Dockerfile chưa có `USER`); chưa có backup riêng cho EFS (bật AWS Backup nếu ảnh quan trọng).
