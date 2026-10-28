"""Storefront (BFF). Mọi dữ liệu lấy qua API của user/catalog/order/promotion-service.
URL, tên route và thông báo hiển thị giữ nguyên như bản monolith."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST  # noqa: F401  (giữ để dễ bật khi cần)

from greenmart.auth import login_required, login_user, logout_user
from greenmart.services import catalog, orders, promotions, users
from greenmart.viewmodel import to_view
from greenmart_common.client import NotFound, ServiceError


# ---------- helpers ----------

def cart_owner(request):
    """Giỏ của user đã đăng nhập, hoặc giỏ vãng lai gắn với session key."""
    if request.user.is_authenticated:
        return {"customer_id": request.user.id}
    if not request.session.session_key:
        request.session.create()
    return {"guest_token": request.session.session_key}


def cart_summary(request):
    return orders.post("/api/carts/current/", json=cart_owner(request))


def cart_count(request):
    return cart_summary(request)["get_cart_items"]


def get_cart(request, prune_hidden=False):
    data = orders.post("/api/carts/current/", json={**cart_owner(request), "detail": True, "prune_hidden": prune_hidden})
    return to_view(data)


def get_product_or_404(slug):
    try:
        return catalog.get(f"/api/products/{slug}/")
    except NotFound:
        raise Http404("Sản phẩm không tồn tại")


def redirect_back(request, default="/"):
    ref = request.META.get("HTTP_REFERER")
    if ref and url_has_allowed_host_and_scheme(ref, allowed_hosts={request.get_host()}):
        return redirect(ref)
    return redirect(default)


# ---------- trang chủ / sản phẩm ----------

def home(request):
    products = to_view(catalog.get("/api/products/", params={"featured": "true"}))
    return render(request, "index.html", {"products": products, "items": cart_count(request)})


def product(request):
    return render(request, "products.html")


def productPage(request):
    categories = to_view(catalog.get("/api/categories/"))
    products = to_view(catalog.get("/api/products/", params={"status": "available"}))
    return render(request, "productPage.html", {"categories": categories, "products": products,
                                                "items": cart_count(request)})


def detail(request, slug):
    data = get_product_or_404(slug)
    reviews = data.pop("reviews", [])
    review_count = data.get("review_count", 0)
    categories = to_view(catalog.get("/api/categories/"))
    return render(request, "detail.html", {
        "product": to_view(data), "categories": categories, "items": cart_count(request),
        "reviews": to_view(reviews), "review_count": review_count,
    })


def search(request):
    query = request.GET.get("q", "").strip()
    products = to_view(catalog.get("/api/products/", params={"q": query})) if query else []
    return render(request, "search.html", {"query": query, "products": products, "items": cart_count(request)})


def policy(request):
    return render(request, "policy.html")


# ---------- giỏ hàng ----------

def cart(request):
    order = get_cart(request, prune_hidden=True)
    return render(request, "cart.html", {
        "order": order,
        "products": order["items"],
        "total_items": order["get_cart_items"],
        "total_money": order["get_cart_total"],
    })


def _change_quantity(request, slug, delta):
    product_ = get_product_or_404(slug)
    orders.post("/api/carts/current/items/", json={**cart_owner(request), "product_id": product_["id"], "delta": delta})
    return product_


def add_to_cart(request, slug):
    product_ = _change_quantity(request, slug, 1)
    messages.success(request, f"✅ {product_['name']} đã được thêm vào giỏ hàng!")
    return redirect_back(request)


def add_to_cart_detail(request, slug):
    product_ = get_product_or_404(slug)
    if request.method != "POST":
        return redirect("detail", slug)
    try:
        quantity = int(request.POST.get("quantity"))
    except (TypeError, ValueError):
        messages.error(request, "Số lượng không hợp lệ.")
        return redirect_back(request)
    orders.post("/api/carts/current/items/", json={**cart_owner(request), "product_id": product_["id"], "delta": quantity})
    messages.success(request, f"✅ {product_['name']} đã được thêm vào giỏ hàng!")
    return redirect_back(request)


def arrow_up(request, slug):
    _change_quantity(request, slug, 1)
    return redirect("cart")


def arrow_down(request, slug):
    _change_quantity(request, slug, -1)
    return redirect("cart")


@login_required
def checkout(request):
    order = get_cart(request)
    if not order["items"]:
        messages.warning(request, "Giỏ hàng đang trống.")
        return redirect("cart")

    profile = users.get(f"/api/users/{request.user.id}/profile/")
    total_money = order["get_total_after_discount"] if order["promotion"] else order["get_cart_total"]
    return render(request, "checkout.html", {
        "order": order,
        "discount_amount": order["get_cart_total"] - total_money,
        "products": order["items"],
        "profile": profile,
        "total_money": total_money,
    })


@login_required
def complete_cart(request):
    try:
        order = to_view(orders.post("/api/orders/complete/", json={"customer_id": request.user.id}))
    except NotFound:
        return render(request, "complete.html", {"order": None})
    total_money = order["get_total_after_discount"] if order["promotion"] else order["get_cart_total"]
    return render(request, "complete.html", {"order": order, "total_money": total_money})


# ---------- khuyến mãi ----------

def promotion_list(request):
    promos = to_view(promotions.get("/api/promotions/", params={"active": "true"}))
    return render(request, "promotions_list.html", {"promotions": promos, "order": to_view(cart_summary(request))})


def use_promotion(request, promo_id):
    try:
        order = to_view(orders.post("/api/carts/current/promotion/", json={**cart_owner(request), "promotion_id": promo_id}))
    except NotFound:
        raise Http404("Mã khuyến mãi không tồn tại")
    except ServiceError as exc:
        error = (exc.data or {}).get("error")
        if error == "cart_empty":
            messages.warning(request, "Giỏ hàng đang trống, chưa thể áp dụng mã.")
        elif error == "min_order_not_met":
            messages.warning(request, "Đơn hàng chưa đạt giá trị tối thiểu để áp dụng mã này.")
        else:
            raise
        return redirect("cart")

    promo = order["promotion"]
    suffix = "%" if promo["discount_type"] == "percent" else "đ"
    messages.success(request, f"🎉 Đã áp dụng mã '{promo['code']}' thành công! Giảm {promo['discount_value']}{suffix}.")
    return redirect("cart")


def cancel_promotion(request, promo_id):
    orders.post("/api/carts/current/promotion/clear/", json=cart_owner(request))
    return redirect("cart")


# ---------- tài khoản ----------

def loginn(request):
    if request.method == "POST":
        try:
            user = users.post("/api/auth/login/", json={
                "username": request.POST.get("fnm"), "password": request.POST.get("password")})
        except ServiceError as exc:
            if exc.status == 401:
                return redirect("loginn")
            raise
        login_user(request, user)
        return redirect("home")
    return render(request, "login.html")


def logout_view(request):
    logout_user(request)
    return redirect("loginn")


REGISTER_ERRORS = {
    "email_exists": "Email đã tồn tại",
    "username_exists": "Tên đăng nhập đã tồn tại",
    "invalid_username": "Tên đăng nhập không được chứa dấu hoặc khoảng trắng",
    "invalid_password": "Mật khẩu không được chứa dấu hoặc khoảng trắng",
}


def register(request):
    if request.method == "POST":
        username = request.POST.get("fnm")
        email = request.POST.get("email")
        password = request.POST.get("pwd")
        if request.POST.get("pwd1") != password:
            # Giữ nguyên thông báo của bản monolith (kể cả việc nó chưa đúng ngữ cảnh).
            messages.error(request, "Tên đăng nhập không được chứa dấu hoặc khoảng trắng")
            return redirect("register")
        try:
            users.post("/api/users/register/", json={"username": username, "email": email, "password": password})
        except ServiceError as exc:
            error = (exc.data or {}).get("error")
            if error in REGISTER_ERRORS:
                messages.error(request, REGISTER_ERRORS[error])
                return redirect("register")
            raise
        return redirect("loginn")
    return render(request, "register.html")


@login_required
def profile_view(request):
    path = f"/api/users/{request.user.id}/profile/"
    if request.method == "POST":
        users.put(path, json={"full_name": request.POST.get("full_name"), "phone": request.POST.get("phone"),
                              "address": request.POST.get("address")})
        messages.success(request, "✅ Cập nhật thông tin thành công!")
        return redirect("profile")
    return render(request, "profile.html", {"profile": users.get(path)})


def password_reset(request):
    if request.method == "POST":
        users.post("/api/password-reset/request/", json={"email": request.POST.get("email", "")})
        return redirect("password_reset_done")
    return render(request, "password_reset.html")


def password_reset_confirm(request, uidb64, token):
    if request.method == "POST":
        try:
            users.post("/api/password-reset/confirm/", json={
                "uid": uidb64, "token": token,
                "new_password1": request.POST.get("new_password1", ""),
                "new_password2": request.POST.get("new_password2", ""),
            })
        except ServiceError as exc:
            if exc.status != 400:
                raise
        else:
            return redirect("password_reset_complete")
    return render(request, "password_reset_confirm.html")


# ---------- đánh giá ----------

REVIEW_ERRORS = {
    "invalid_rating": "Số sao phải từ 1 đến 5.",
    "empty_comment": "Vui lòng nhập nội dung đánh giá.",
}


@login_required
def add_review(request, slug):
    if request.method == "POST":
        try:
            rating = int(request.POST.get("rating", 0))
        except (TypeError, ValueError):
            rating = 0
        try:
            catalog.post(f"/api/products/{slug}/reviews/", json={
                "user_id": request.user.id, "username": request.user.username, "rating": rating,
                "comment": request.POST.get("comment", "").strip()})
        except NotFound:
            raise Http404("Sản phẩm không tồn tại")
        except ServiceError as exc:
            error = (exc.data or {}).get("error")
            if error not in REVIEW_ERRORS:
                raise
            messages.error(request, REVIEW_ERRORS[error])
        else:
            messages.success(request, "Đánh giá của bạn đã được gửi thành công!")
    return redirect("detail", slug)


@login_required
def reply_review(request, review_id):
    slug = None
    if request.method == "POST":
        try:
            data = catalog.post(f"/api/reviews/{review_id}/reply/", json={
                "user_id": request.user.id, "username": request.user.username,
                "content": request.POST.get("content")})
            slug = data["product_slug"]
        except NotFound:
            raise Http404("Đánh giá không tồn tại")
        except ServiceError as exc:
            slug = (exc.data or {}).get("product_slug")
            if not slug:
                raise
    if not slug:
        raise Http404("Đánh giá không tồn tại")
    return redirect("detail", slug=slug)
