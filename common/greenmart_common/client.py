"""HTTP client gọi service khác trong mạng nội bộ."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ServiceError(Exception):
    """Service trả về lỗi 4xx/5xx."""

    def __init__(self, status, data=None, service=""):
        self.status = status
        self.data = data or {}
        self.service = service
        super().__init__(f"[{service}] HTTP {status}: {self.data}")


class NotFound(ServiceError):
    pass


class ServiceUnavailable(ServiceError):
    """Không kết nối được / timeout / 5xx."""


class ServiceClient:
    def __init__(self, name, base_url, token, timeout=(2, 8)):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"X-Internal-Token": token, "Accept": "application/json"})
        # Chỉ retry GET (idempotent) khi gateway/service tạm lỗi.
        retry = Retry(total=2, backoff_factor=0.2, status_forcelist=(502, 503, 504),
                      allowed_methods=frozenset({"GET"}), raise_on_status=False)
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def request(self, method, path, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = self.session.request(method, self.base_url + path, **kwargs)
        except requests.RequestException as exc:
            raise ServiceUnavailable(503, {"detail": str(exc)}, self.name) from exc
        try:
            data = resp.json() if resp.content else None
        except ValueError:
            data = {"detail": resp.text[:200]}
        if resp.status_code == 404:
            raise NotFound(404, data, self.name)
        if resp.status_code >= 500:
            raise ServiceUnavailable(resp.status_code, data, self.name)
        if resp.status_code >= 400:
            raise ServiceError(resp.status_code, data, self.name)
        return data

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def put(self, path, **kw):
        return self.request("PUT", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)
