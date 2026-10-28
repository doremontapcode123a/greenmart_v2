from django.db import connection
from django.http import JsonResponse


def make_health_view(service_name):
    def health(request):
        try:
            connection.ensure_connection()
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
        except Exception as exc:  # noqa: BLE001
            return JsonResponse({"service": service_name, "status": "error", "detail": str(exc)}, status=503)
        return JsonResponse({"service": service_name, "status": "ok"})

    return health
