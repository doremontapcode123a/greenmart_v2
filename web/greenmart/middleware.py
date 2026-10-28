import logging
import time

from django.shortcuts import render

from greenmart_common.client import NotFound, ServiceUnavailable

from .auth import AnonymousUser, SessionUser
from .services import users

log = logging.getLogger(__name__)

REVALIDATE_SECONDS = 60


class RemoteUserMiddleware:
    """Gắn request.user từ session. Cứ ~60s hỏi lại user-service để phát hiện tài khoản bị khóa/xóa/đổi quyền."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = self._resolve(request)
        return self.get_response(request)

    def _resolve(self, request):
        data = request.session.get("user")
        if not data:
            return AnonymousUser()
        if time.time() - data.get("checked_at", 0) > REVALIDATE_SECONDS:
            try:
                fresh = users.get(f"/api/users/{data['id']}/")
            except NotFound:
                request.session.flush()
                return AnonymousUser()
            except ServiceUnavailable:
                log.warning("user-service không phản hồi; tạm dùng danh tính trong session")
            else:
                if not fresh["is_active"]:
                    request.session.flush()
                    return AnonymousUser()
                data.update(username=fresh["username"], email=fresh["email"], is_staff=fresh["is_staff"],
                            is_superuser=fresh["is_superuser"], checked_at=time.time())
                request.session["user"] = data
        return SessionUser(data)


class ServiceErrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, ServiceUnavailable):
            log.error("Service phụ thuộc không khả dụng: %s", exception)
            return render(request, "service_unavailable.html", {"service": exception.service}, status=503)
        return None
