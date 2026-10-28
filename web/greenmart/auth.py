"""Xác thực phía web: danh tính user nằm trong session (do user-service xác nhận), không có bảng user cục bộ."""
import functools
import logging
import time
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect

from greenmart_common.client import ServiceError

from .services import orders

log = logging.getLogger(__name__)


class SessionUser:
    is_authenticated = True
    is_anonymous = False

    def __init__(self, data):
        self.id = self.pk = data["id"]
        self.username = data["username"]
        self.email = data.get("email", "")
        self.is_staff = data.get("is_staff", False)
        self.is_superuser = data.get("is_superuser", False)

    def __str__(self):
        return self.username


class AnonymousUser:
    is_authenticated = False
    is_anonymous = True
    id = pk = None
    username = ""
    email = ""
    is_staff = False
    is_superuser = False

    def __str__(self):
        return "AnonymousUser"


def login_user(request, user):
    """Ghi user vào session, đổi session key (chống session fixation) và gộp giỏ hàng khách vãng lai."""
    guest_token = request.session.session_key
    request.session.cycle_key()
    request.session["user"] = {
        "id": user["id"], "username": user["username"], "email": user.get("email", ""),
        "is_staff": user.get("is_staff", False), "is_superuser": user.get("is_superuser", False),
        "checked_at": time.time(),
    }
    request.user = SessionUser(request.session["user"])
    if guest_token:
        try:
            orders.post("/api/carts/merge/", json={"guest_token": guest_token, "customer_id": user["id"]})
        except ServiceError:
            log.warning("Không gộp được giỏ hàng khách vãng lai sau khi đăng nhập", exc_info=True)


def logout_user(request):
    request.session.flush()
    request.user = AnonymousUser()


def login_required(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={quote(request.get_full_path())}")
        return view(request, *args, **kwargs)
    return wrapper


def staff_required(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return redirect("admin_login")
        return view(request, *args, **kwargs)
    return wrapper
