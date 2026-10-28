"""Admin panel (BFF). Mọi view đều yêu cầu tài khoản staff (bản monolith chỉ bảo vệ một phần)."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from greenmart.auth import login_user, logout_user, staff_required
from greenmart.services import catalog, orders, promotions, users
from greenmart.viewmodel import to_view
from greenmart_common.client import NotFound, ServiceError


# ---------- helpers ----------

def attach_customers(order_list):
    """Gắn thông tin khách hàng (kèm hồ sơ) vào đơn hàng: order['customer'] = {username, profile{...}} hoặc None."""
    ids = sorted({o["customer_id"] for o in order_list if o["customer_id"]})
    found = {}
    if ids:
        found = {u["id"]: u for u in users.get("/api/users/", params={"ids": ",".join(map(str, ids)), "include": "profile"})}
    for o in order_list:
        o["customer"] = found.get(o["customer_id"])
    return order_list


def error_text(exc):
    """Gom thông báo lỗi validate từ service thành 1 chuỗi."""
    errors = (exc.data or {}).get("errors")
    if isinstance(errors, dict):
        return "; ".join(f"{k}: {' '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in errors.items())
    return str((exc.data or {}).get("error") or exc)


def product_form_fields(request):
    fields = {
        "name": request.POST.get("name"),
        "category_id": request.POST.get("category"),
        "price": request.POST.get("price"),
        "unit": request.POST.get("unit"),
        "stock": request.POST.get("stock"),
        "status": request.POST.get("status"),
        "description": request.POST.get("description", ""),
        "is_featured": "true" if request.POST.get("is_featured") == "on" else "false",
    }
    if request.POST.get("origin") is not None:
        fields["origin"] = request.POST.get("origin")
    return {k: v for k, v in fields.items() if v is not None}


def uploaded_image(request):
    image = request.FILES.get("image")
    if not image:
        return None
    return {"image": (image.name, image.read(), image.content_type or "application/octet-stream")}


# ---------- đăng nhập ----------

def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("admin_dashboard")
    if request.method == "POST":
        try:
            user = users.post("/api/auth/login/", json={
                "username": request.POST.get("username"), "password": request.POST.get("password")})
        except ServiceError as exc:
            if exc.status != 401:
                raise
            user = None
        if user and user["is_staff"]:
            login_user(request, user)
            return redirect("admin_dashboard")
        messages.error(request, "Tên đăng nhập hoặc mật khẩu không hợp lệ!")
    return render(request, "loginn.html")


def logout_view(request):
    logout_user(request)
    return redirect("loginn")


# ---------- dashboard / danh sách ----------

@staff_required
def dashboard(request):
    stats = {}
    stats.update(catalog.get("/api/stats/"))
    stats.update(orders.get("/api/orders/stats/"))
    stats.update(users.get("/api/users/stats/"))
    return render(request, "dashboard.html", {
        "product_count": stats["product_count"], "category_count": stats["category_count"],
        "order_count": stats["order_count"], "user_count": stats["user_count"],
    })


@staff_required
def product_list(request):
    products = to_view(catalog.get("/api/products/", params={"ordering": "-created_at"}))
    return render(request, "product.html", {"products": products})


@staff_required
def order_list(request):
    order_list_ = attach_customers(to_view(orders.get("/api/orders/", params={"complete": "true"})))
    return render(request, "orders.html", {"orders": order_list_})


@staff_required
def orders_complete(request):
    order_list_ = attach_customers(to_view(orders.get(
        "/api/orders/", params={"complete": "true", "ordering": "-date_order"})))
    return render(request, "ordersComplete.html", {"orders": order_list_})


@staff_required
def user_list(request):
    return render(request, "users.html", {"users": to_view(users.get("/api/users/"))})


@staff_required
def toggle_user_status(request, user_id):
    try:
        user = users.post(f"/api/users/{user_id}/toggle-active/")
    except NotFound:
        raise Http404("Người dùng không tồn tại")
    status = "mở khóa" if user["is_active"] else "khóa"
    messages.success(request, f"Tài khoản {user['username']} đã được {status}.")
    return redirect("admin_users")


# ---------- sản phẩm ----------

@staff_required
def add_product(request):
    categories = to_view(catalog.get("/api/categories/"))
    if request.method == "POST":
        try:
            product = catalog.post("/api/products/", data=product_form_fields(request), files=uploaded_image(request))
        except ServiceError as exc:
            if exc.status != 400:
                raise
            if "category_id" in ((exc.data or {}).get("errors") or {}):
                messages.error(request, "❌ Danh mục không hợp lệ!")
            else:
                messages.error(request, f"⚠️ Lỗi: {error_text(exc)}")
        else:
            messages.success(request, f"✅ Sản phẩm '{product['name']}' đã được thêm thành công!")
            return redirect("admin_products")
    return render(request, "AddProduct.html", {"categories": categories})


@staff_required
def edit_product(request, slug):
    try:
        product = catalog.get(f"/api/products/{slug}/")
    except NotFound:
        raise Http404("Sản phẩm không tồn tại")
    categories = to_view(catalog.get("/api/categories/"))

    if request.method == "POST":
        try:
            updated = catalog.put(f"/api/products/{slug}/", data=product_form_fields(request), files=uploaded_image(request))
        except ServiceError as exc:
            if exc.status != 400:
                raise
            if "category_id" in ((exc.data or {}).get("errors") or {}):
                messages.error(request, "❌ Danh mục không hợp lệ!")
            else:
                messages.error(request, f"⚠️ Lỗi: {error_text(exc)}")
        else:
            messages.success(request, f"✅ Sản phẩm '{updated['name']}' đã được sửa thành công!")
            return redirect("admin_products")
    return render(request, "editProduct.html", {"categories": categories, "product": to_view(product)})


@staff_required
def delete_product(request, slug):
    try:
        product = catalog.post(f"/api/products/{slug}/hide/")
    except NotFound:
        raise Http404("Sản phẩm không tồn tại")
    # Không xóa dữ liệu thật: chỉ ẩn sản phẩm và đưa tồn kho về 0.
    messages.success(request, f"Đã ẩn sản phẩm {product['name']}")
    return redirect("admin_products")


# ---------- khuyến mãi ----------

@staff_required
def promotion(request):
    return render(request, "promotion.html", {"promotions": to_view(promotions.get("/api/promotions/"))})


@staff_required
def edit_promotion(request, id):
    # Giống bản monolith: trang này chỉ hiển thị form, chưa có xử lý lưu.
    try:
        promo = to_view(promotions.get(f"/api/promotions/{id}/"))
    except NotFound:
        raise Http404("Khuyến mãi không tồn tại")
    return render(request, "editPromotion.html", {"promotion": promo})


@staff_required
def add_promotion(request):
    if request.method == "POST":
        payload = {
            "name": request.POST.get("name"),
            "code": request.POST.get("code"),
            "discount_type": request.POST.get("discount_type"),
            "discount_value": request.POST.get("discount_value"),
            "apply_type": request.POST.get("apply_type"),
            "start_date": request.POST.get("start_date") or None,
            "end_date": request.POST.get("end_date") or None,
            "min_order_value": request.POST.get("min_order_value") or 0,
        }
        try:
            promotions.post("/api/promotions/", json=payload)
        except ServiceError as exc:
            if exc.status != 400:
                raise
            messages.error(request, f"❌ Lỗi khi thêm khuyến mãi: {error_text(exc)}")
        else:
            messages.success(request, f"✅ Đã thêm khuyến mãi '{payload['name']}' thành công!")
            return redirect("admin_promotion")
    return render(request, "addPromotion.html", {"promotion": to_view(promotions.get("/api/promotions/"))})


@staff_required
def delete_promotion(request, id):
    promotions.delete(f"/api/promotions/{id}/")
    return redirect("admin_promotion")
