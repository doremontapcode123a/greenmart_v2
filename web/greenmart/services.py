"""Client tới các service nội bộ (dùng chung một Session/connection pool cho mỗi service)."""
from django.conf import settings

from greenmart_common.client import ServiceClient

users = ServiceClient("user-service", settings.USER_SERVICE_URL, settings.INTERNAL_API_TOKEN)
catalog = ServiceClient("catalog-service", settings.CATALOG_SERVICE_URL, settings.INTERNAL_API_TOKEN, timeout=(2, 15))
orders = ServiceClient("order-service", settings.ORDER_SERVICE_URL, settings.INTERNAL_API_TOKEN)
promotions = ServiceClient("promotion-service", settings.PROMOTION_SERVICE_URL, settings.INTERNAL_API_TOKEN)
