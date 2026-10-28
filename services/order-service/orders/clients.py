from django.conf import settings

from greenmart_common.client import ServiceClient

catalog = ServiceClient("catalog-service", settings.CATALOG_SERVICE_URL, settings.INTERNAL_API_TOKEN)
promotions = ServiceClient("promotion-service", settings.PROMOTION_SERVICE_URL, settings.INTERNAL_API_TOKEN)


def fetch_products(ids):
    """Lấy thông tin sản phẩm hiện tại (giá, tên, trạng thái...) theo lô -> {id: product}."""
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    data = catalog.get("/api/products/", params={"ids": ",".join(str(i) for i in ids)})
    return {p["id"]: p for p in data}
