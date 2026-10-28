"""Xác thực service-to-service bằng token nội bộ.

Các service domain KHÔNG được publish ra ngoài gateway; chỉ web (BFF) và các service
gọi nhau trong mạng nội bộ, kèm header X-Internal-Token.
"""
import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class IsInternalService(BasePermission):
    message = "Thiếu hoặc sai internal service token."

    def has_permission(self, request, view):
        expected = getattr(settings, "INTERNAL_API_TOKEN", "") or ""
        provided = request.headers.get("X-Internal-Token", "")
        return bool(expected) and hmac.compare_digest(provided.encode(), expected.encode())
