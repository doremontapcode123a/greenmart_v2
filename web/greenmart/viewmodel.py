"""JSON từ service -> dữ liệu cho template.

Template cũ dùng datetime/Decimal (|date:"d/m/Y", phép trừ tiền...). API trả chuỗi ISO / chuỗi số,
nên chuyển lại ở đây để template giữ nguyên.
"""
from decimal import Decimal

from django.utils.dateparse import parse_datetime

DECIMAL_KEYS = {
    "price", "get_total", "get_cart_total", "get_discount_amount", "get_total_after_discount",
    "discount_value", "min_order_value",
}


def to_view(obj):
    if isinstance(obj, list):
        return [to_view(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if isinstance(value, str) and key in DECIMAL_KEYS:
                out[key] = Decimal(value)
            elif isinstance(value, str) and (key.endswith("_at") or key.startswith("date_") or key.endswith("_date")):
                out[key] = parse_datetime(value) or value
            else:
                out[key] = to_view(value)
        return out
    return obj
