"""DRF exception handler: chuyển lỗi gọi service khác thành 503/502 có cấu trúc."""
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .client import ServiceError, ServiceUnavailable


def exception_handler(exc, context):
    if isinstance(exc, ServiceUnavailable):
        return Response({"error": "upstream_unavailable", "service": exc.service}, status=503)
    if isinstance(exc, ServiceError):
        return Response({"error": "upstream_error", "service": exc.service, "status": exc.status}, status=502)
    return drf_exception_handler(exc, context)
