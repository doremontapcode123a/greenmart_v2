def user(request):
    """Thay cho context processor 'auth' của Django: template vẫn dùng {{ user.is_authenticated }}."""
    return {"user": getattr(request, "user", None)}
