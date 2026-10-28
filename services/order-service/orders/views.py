from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from rest_framework.response import Response
from rest_framework.views import APIView

from greenmart_common.client import NotFound

from .clients import fetch_products, promotions
from .models import Order, OrderItem
from .pricing import promotion_snapshot_dict, serialize_order


# ---------- helpers ----------

class BadOwner(Exception):
    pass


def parse_owner(data):
    """(customer_id, guest_token). Đúng một trong hai."""
    cid = data.get("customer_id")
    token = data.get("guest_token")
    if cid not in (None, ""):
        try:
            return int(cid), None
        except (TypeError, ValueError):
            raise BadOwner()
    if token:
        return None, str(token)[:64]
    raise BadOwner()


def get_or_create_cart(customer_id, guest_token):
    qs = Order.objects.filter(complete=False)
    if customer_id is not None:
        qs = qs.filter(customer_id=customer_id)
    else:
        qs = qs.filter(customer_id__isnull=True, guest_token=guest_token)
    order = qs.order_by("id").first()
    if order is None:
        order = Order.objects.create(customer_id=customer_id, guest_token=guest_token, complete=False)
    return order


def full_order(order):
    products = fetch_products(i.product_id for i in order.items.all()) if _needs_live_prices(order) else {}
    return serialize_order(order, products)


def _needs_live_prices(order):
    if not order.complete:
        return True
    return any(i.unit_price is None for i in order.items.all())


def bad_owner_response():
    return Response({"error": "invalid_owner"}, status=400)


# ---------- giỏ hàng ----------

class CurrentCartView(APIView):
    """POST {customer_id | guest_token, detail?, prune_hidden?} -> giỏ đang mở (tạo nếu chưa có)."""

    def post(self, request):
        try:
            cid, token = parse_owner(request.data)
        except BadOwner:
            return bad_owner_response()
        order = get_or_create_cart(cid, token)

        if not request.data.get("detail"):
            count = order.items.aggregate(s=Sum("quantity"))["s"] or 0
            return Response({"id": order.id, "customer_id": order.customer_id, "get_cart_items": count,
                             "promotion": promotion_snapshot_dict(order)})

        products = fetch_products(i.product_id for i in order.items.all())
        if request.data.get("prune_hidden"):
            # Sản phẩm bị ẩn/đã mất khỏi catalog thì loại khỏi giỏ (bản cũ làm việc này ở view giỏ hàng).
            stale = [i.id for i in order.items.all()
                     if i.product_id not in products or products[i.product_id]["status"] == "hidden"]
            if stale:
                OrderItem.objects.filter(pk__in=stale).delete()
        order = Order.objects.prefetch_related("items").get(pk=order.pk)
        return Response(serialize_order(order, products))


class CartItemView(APIView):
    """POST {owner, product_id, delta} -> cộng/trừ số lượng; <= 0 thì xóa dòng."""

    def post(self, request):
        try:
            cid, token = parse_owner(request.data)
            product_id = int(request.data.get("product_id"))
            delta = int(request.data.get("delta", 1))
        except (BadOwner, TypeError, ValueError):
            return Response({"error": "invalid_request"}, status=400)

        with transaction.atomic():
            order = get_or_create_cart(cid, token)
            item, _ = OrderItem.objects.get_or_create(order=order, product_id=product_id, defaults={"quantity": 0})
            OrderItem.objects.filter(pk=item.pk).update(quantity=F("quantity") + delta)
            item.refresh_from_db()
            removed = item.quantity <= 0
            if removed:
                item.delete()
        count = order.items.aggregate(s=Sum("quantity"))["s"] or 0
        return Response({"order_id": order.id, "removed": removed, "get_cart_items": count})


class ApplyPromotionView(APIView):
    """POST {owner, promotion_id}. 404 nếu mã không tồn tại/đang tắt; 409 nếu giỏ trống hoặc chưa đủ giá trị tối thiểu."""

    def post(self, request):
        try:
            cid, token = parse_owner(request.data)
            promo_id = int(request.data.get("promotion_id"))
        except (BadOwner, TypeError, ValueError):
            return Response({"error": "invalid_request"}, status=400)
        try:
            promo = promotions.get(f"/api/promotions/{promo_id}/")
        except NotFound:
            return Response({"error": "promotion_not_found"}, status=404)
        if not promo["is_active"]:
            return Response({"error": "promotion_not_found"}, status=404)

        order = get_or_create_cart(cid, token)
        data = full_order(order)
        if not data["items"]:
            return Response({"error": "cart_empty"}, status=409)
        if Decimal(data["get_cart_total"]) < Decimal(promo["min_order_value"]):
            return Response({"error": "min_order_not_met", "min_order_value": promo["min_order_value"]}, status=409)

        order.set_promotion(promo)
        order.save()
        return Response(full_order(Order.objects.prefetch_related("items").get(pk=order.pk)))


class ClearPromotionView(APIView):
    def post(self, request):
        try:
            cid, token = parse_owner(request.data)
        except BadOwner:
            return bad_owner_response()
        order = get_or_create_cart(cid, token)
        order.clear_promotion()
        order.save()
        return Response({"id": order.id})


class MergeCartView(APIView):
    """Khi khách đăng nhập: gộp giỏ vãng lai (guest_token) vào giỏ của user, rồi xóa giỏ vãng lai."""

    def post(self, request):
        token = request.data.get("guest_token")
        try:
            customer_id = int(request.data.get("customer_id"))
        except (TypeError, ValueError):
            return Response({"error": "invalid_request"}, status=400)
        if not token:
            return Response({"merged": False})
        with transaction.atomic():
            guest = Order.objects.filter(customer_id__isnull=True, guest_token=token, complete=False).first()
            if guest is None:
                return Response({"merged": False})
            user_order = get_or_create_cart(customer_id, None)
            for item in guest.items.all():
                user_item, created = OrderItem.objects.get_or_create(
                    order=user_order, product_id=item.product_id, defaults={"quantity": item.quantity})
                if not created:
                    user_item.quantity = (user_item.quantity or 0) + (item.quantity or 0)
                    user_item.save()
            guest.delete()
        return Response({"merged": True})


# ---------- đơn hàng ----------

class CompleteOrderView(APIView):
    """POST {customer_id}: chốt giỏ đang mở thành đơn hoàn tất, lưu snapshot tên/giá từng dòng."""

    def post(self, request):
        try:
            customer_id = int(request.data.get("customer_id"))
        except (TypeError, ValueError):
            return Response({"error": "invalid_request"}, status=400)
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(customer_id=customer_id, complete=False).order_by("id").first()
            if order is None:
                return Response({"error": "no_open_cart"}, status=404)
            products = fetch_products(i.product_id for i in order.items.all())
            for item in order.items.all():
                p = products.get(item.product_id)
                if p:
                    item.product_name = p["name"]
                    item.product_slug = p["slug"]
                    item.unit_price = Decimal(p["price"])
                    item.save()
            order.complete = True
            order.save()
        order = Order.objects.prefetch_related("items").get(pk=order.pk)
        return Response(serialize_order(order, products))


class OrderListView(APIView):
    """GET ?complete=true|false&customer_id=&ordering=-date_order"""

    ORDERING = {"id", "-id", "date_order", "-date_order"}

    def get(self, request):
        p = request.query_params
        qs = Order.objects.prefetch_related("items")
        if p.get("complete") in ("true", "1"):
            qs = qs.filter(complete=True)
        elif p.get("complete") in ("false", "0"):
            qs = qs.filter(complete=False)
        if p.get("customer_id"):
            qs = qs.filter(customer_id=p["customer_id"])
        ordering = p.get("ordering", "id")
        orders = list(qs.order_by(ordering if ordering in self.ORDERING else "id"))

        live_ids = [i.product_id for o in orders if _needs_live_prices(o) for i in o.items.all()]
        products = fetch_products(live_ids) if live_ids else {}
        return Response([serialize_order(o, products) for o in orders])


class StatsView(APIView):
    def get(self, request):
        return Response({"order_count": Order.objects.count()})
