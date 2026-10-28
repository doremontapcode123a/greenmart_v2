"""Tính tiền & dựng JSON cho đơn hàng. Quy tắc giữ nguyên theo bản monolith (Order/OrderItem/Promotion.get_discount)."""
from decimal import Decimal

ZERO = Decimal("0.00")


def _dec(value):
    return Decimal(str(value)) if value is not None else ZERO


def discount_amount(order, total):
    """Tương đương Order.get_discount_amount -> Promotion.get_discount(order_total) (không truyền items):
    chỉ khuyến mãi 'Toàn đơn hàng' mới sinh ra số tiền giảm khi hiển thị."""
    if not order.promotion_id:
        return ZERO
    if total < _dec(order.promotion_min_order_value):
        return ZERO
    discount = ZERO
    value = _dec(order.promotion_discount_value)
    if order.promotion_apply_type == "order":
        if order.promotion_discount_type == "money":
            discount = min(value, total)
        elif order.promotion_discount_type == "percent":
            discount = total * (value / 100)
    return round(discount, 2)


DISCOUNT_TYPE_LABELS = {"money": "Giảm theo số tiền", "percent": "Giảm theo phần trăm"}
APPLY_TYPE_LABELS = {"product": "Theo sản phẩm", "category": "Theo danh mục", "order": "Toàn đơn hàng"}


def promotion_snapshot_dict(order):
    if not order.promotion_id:
        return None
    return {
        "id": order.promotion_id,
        "code": order.promotion_code,
        "name": order.promotion_name,
        "discount_type": order.promotion_discount_type,
        "get_discount_type_display": DISCOUNT_TYPE_LABELS.get(order.promotion_discount_type, ""),
        "discount_value": str(order.promotion_discount_value),
        "apply_type": order.promotion_apply_type,
        "get_apply_type_display": APPLY_TYPE_LABELS.get(order.promotion_apply_type, ""),
        "min_order_value": str(order.promotion_min_order_value),
    }


def item_rows(order, products_by_id):
    """-> list[(item, product_dict|None, unit_price|None)]"""
    rows = []
    for item in order.items.all():
        if order.complete and item.unit_price is not None:
            product = {"id": item.product_id, "name": item.product_name, "slug": item.product_slug,
                       "price": str(item.unit_price)}
            price = item.unit_price
        else:
            product = (products_by_id or {}).get(item.product_id)
            price = Decimal(product["price"]) if product else None
        rows.append((item, product, price))
    return rows


def serialize_order(order, products_by_id=None):
    rows = item_rows(order, products_by_id)
    items = []
    cart_total = ZERO
    cart_items = 0
    for item, product, price in rows:
        qty = item.quantity or 0
        line_total = price * qty if price is not None else ZERO
        cart_total += line_total
        cart_items += qty
        items.append({
            "id": item.id,
            "quantity": item.quantity,
            "date_added": item.date_added,
            "product": product,
            "get_total": str(line_total),
        })
    discount = discount_amount(order, cart_total)
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "date_order": order.date_order,
        "complete": order.complete,
        "transaction_id": order.transaction_id,
        "promotion": promotion_snapshot_dict(order),
        "items": items,
        "get_cart_items": cart_items,
        "get_cart_total": str(cart_total),
        "get_discount_amount": str(discount),
        "get_total_after_discount": str(cart_total - discount),
    }
