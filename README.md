# GreenMart – bản microservice + MySQL

Chuyển từ Django monolith (SQLite) sang các service độc lập, mỗi service một database MySQL riêng.
Giao diện, URL, tên route và thông báo hiển thị của storefront / admin panel được giữ nguyên.

## Kiến trúc

```
                         ┌────────────────────────── gateway (nginx) :8088 ──────────────────────────┐
 trình duyệt ──────────► │ /static,/media  → volume     /admin/ → user-service    /admin/catalog/ → catalog-service
                         │ mọi đường dẫn khác → web (BFF) │
                         └───────────────────────────────────────────────────────────────────────────┘
                                         web (BFF: storefront + /admin_panel/, session ở web_db)
                      ┌──────────────┬──────────────┼───────────────┬─────────────────┐
                 user-service   catalog-service   order-service   promotion-service     (REST/JSON, header X-Internal-Token)
                   user_db        catalog_db         order_db       promotion_db  ──►  cùng một MySQL 8, mỗi DB một tài khoản riêng
                                                  │  ▲   ▲
                                                  └──┴───┴── order-service gọi catalog (giá/tên SP) và promotion (kiểm tra mã)
```

| Service | Sở hữu | Ghi chú |
|---|---|---|
| **user-service** | `auth_user` (giữ nguyên hash mật khẩu), `UserProfile`, đăng nhập/đăng ký, khóa tài khoản, đặt lại mật khẩu (gửi mail) | Django admin tại `/admin/` |
| **catalog-service** | Category, Product (+ upload ảnh), Review | Django admin tại `/admin/catalog/` (quản lý danh mục, đánh giá) |
| **order-service** | Order, OrderItem: giỏ hàng, gộp giỏ khi đăng nhập, áp mã, hoàn tất đơn | Gọi catalog (giá) và promotion (mã) |
| **promotion-service** | Promotion | |
| **web (BFF)** | Template storefront + admin panel; không có dữ liệu nghiệp vụ | Session lưu ở `web_db`; danh tính xác nhận lại với user-service mỗi ~60s |
| **gateway** | nginx, cổng duy nhất mở ra ngoài | |

Quy ước: không có khóa ngoại giữa các database – chỉ lưu `user_id`, `product_id`… (Review lưu thêm `username`).
Các service nội bộ chỉ nhận request có `X-Internal-Token` đúng (không có token → 403) và không publish port.

## Chạy

```bash
cp .env.example .env        # điền SECRET_KEY, INTERNAL_API_TOKEN, mật khẩu DB… (xem hướng dẫn sinh chuỗi trong file)
docker compose up -d --build
# → http://localhost:8088          (storefront)
#   http://localhost:8088/admin_panel/   (admin panel, cần tài khoản is_staff)
#   http://localhost:8088/admin/         (Django admin: user)   /admin/catalog/ (Django admin: catalog)
```

### Kubernetes

Manifest Kustomize nằm trong `k8s/` – xem `k8s/README.md` (build image, tạo Secret, apply, migrate, chuyển dữ liệu).
Amazon EKS (RDS + EBS + ECR, chạy HTTP): hạ tầng bằng Terraform ở `infra/terraform/`, overlay `k8s/overlays/eks/`, runbook ở `k8s/overlays/eks/README.md`.
Cluster EKS mới tạo: `infra/eks-bootstrap/` tự cài OIDC provider + AWS Load Balancer Controller + app mẫu 2048 (Jenkinsfile / GitHub Actions / script).

### Chuyển dữ liệu từ `db.sqlite3` cũ

```bash
mkdir -p legacy && cp /đường/dẫn/db.sqlite3 legacy/
docker compose up -d                                   # để các service tự migrate tạo bảng
docker compose --profile tools run --rm data-migrator --dry-run     # chỉ thống kê
docker compose --profile tools run --rm data-migrator --truncate    # nạp thật (ghi đè dữ liệu đích)
```
Script giữ nguyên ID và mật khẩu (đăng nhập như cũ). Với dữ liệu mẫu đã kiểm tra: 4 user, 9 sản phẩm, 37 đơn, 48 dòng đơn.
Bỏ qua 2.344 giỏ hàng khách vãng lai trống và 23 order item mồ côi (không thuộc order nào).
Đơn đã hoàn tất được chốt tên/giá theo **giá hiện tại** của sản phẩm (dữ liệu cũ không lưu giá lúc mua).
Ảnh sản phẩm cũ đã nằm sẵn trong `media/products/` (tên file tiếng Việt đã được giải mã lại cho khớp với đường dẫn trong DB).

### Test

`tests/e2e_smoke.py` đi qua web như trình duyệt (khách → đăng ký → đăng nhập/gộp giỏ → khuyến mãi → thanh toán → đánh giá →
reset mật khẩu → admin: thêm/sửa/ẩn sản phẩm có ảnh, khuyến mãi, khóa user):
`BASE=http://localhost:8088 ADMIN_USER=<staff> ADMIN_PASSWORD=<mk> python tests/e2e_smoke.py` (tạo dữ liệu thử, chỉ chạy trên dev/staging).

## Khác biệt so với bản monolith (cần biết / cần review)

**Bắt buộc phải đổi khi sang MySQL**
- `Promotion.discount_value` khai báo `max_digits=100000000`: SQLite bỏ qua nhưng MySQL giới hạn DECIMAL ≤ 65 chữ số nên migrate sẽ lỗi → đổi thành `max_digits=12`.
- MySQL so sánh chuỗi **không phân biệt hoa/thường**: username `Admin` và `admin` coi là một; đăng nhập, slug, email cũng vậy.
- Quyền chi tiết (Group/Permission) của user **không** được chuyển; chỉ giữ `is_staff`/`is_superuser`.

**Thay đổi hành vi (có chủ đích)**
- Mọi trang `/admin_panel/*` yêu cầu tài khoản staff (trước đây chỉ 2/13 view được bảo vệ – ai cũng vào được dashboard/sản phẩm/đơn hàng).
- Giỏ khách vãng lai: trước đây `add_to_cart_detail`, `arrow_up`, `arrow_down` dùng chung **một** giỏ `customer=None` cho mọi khách; nay mỗi session một giỏ.
- Đơn hoàn tất lưu snapshot tên/giá từng dòng; mã khuyến mãi lưu snapshot lúc áp mã (đổi giá/tắt mã sau đó không làm đổi đơn cũ).
- `/profile/` và `/complete/` chuyển hướng sang đăng nhập khi chưa login (trước đây lỗi 500). Link `detail/<slug>` không tồn tại trả 404 thay vì 500.
- Sản phẩm bị ẩn khỏi giỏ được loại **trước** khi tính tổng tiền.
- Django admin cho Order/Promotion không còn; quản trị qua `/admin_panel/`.

**Giữ nguyên như cũ (lỗi sẵn có, chưa sửa)**
- Đăng ký: mật khẩu nhập lại không khớp vẫn hiện thông báo "Tên đăng nhập không được chứa dấu hoặc khoảng trắng".
- Tìm kiếm vẫn trả cả sản phẩm đã ẩn; trang sửa khuyến mãi chỉ hiển thị form (chưa lưu); `start_date` của khuyến mãi luôn là thời điểm tạo.
- Khuyến mãi loại "theo sản phẩm/danh mục" cho phép áp mã nhưng số tiền giảm hiển thị là 0 (chỉ loại "toàn đơn hàng" có giảm giá).
- Trang `checkout` có form POST không xử lý gì (nút hoàn tất là link tới `/complete/`).

## Bảo mật – cần xử lý ngay
- `greenmart/settings.py` cũ commit sẵn **mật khẩu ứng dụng Gmail** và `SECRET_KEY`; chúng nằm trong lịch sử git. Hãy **thu hồi/đổi mật khẩu ứng dụng Gmail đó** và đặt SECRET_KEY mới. Bản mới đọc mọi bí mật từ `.env`.
- `DEBUG=True` và `ALLOWED_HOSTS=['*']` ở bản cũ; bản mới mặc định `DEBUG=False`.

## Chưa làm / chưa kiểm chứng
- **Chưa build thử Docker image / `docker compose up`** (môi trường tạo ra không có Docker). Đã kiểm chứng: toàn bộ 5 service chạy bằng gunicorn trên MariaDB 10.11, migrate sạch, script chuyển dữ liệu chạy với dữ liệu thật, bộ test e2e đạt toàn bộ, `collectstatic` OK, cú pháp compose/shell hợp lệ. Production dùng MySQL 8 – khuyến nghị chạy e2e một lần sau khi `compose up`.
- **Manifest K8s** đã validate schema nhưng chưa chạy trên cluster thật.
- **CI/CD (Jenkins, GitHub Actions, ECS) chưa chuyển đổi** – xem `deploy/legacy-monolith/README.md`.
- Chưa có giới hạn số lần đăng nhập sai, chưa có cache/phân trang cho danh sách sản phẩm (như bản cũ).
- Nếu service phụ thuộc chết, web hiển thị trang 503 thân thiện; chưa có circuit breaker/retry nâng cao (chỉ retry GET 2 lần).
