import uuid

from django.db import models


class Order(models.Model):
    # customer thuộc user-service => chỉ lưu id. Khách vãng lai dùng guest_token (session key của web).
    customer_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    guest_token = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    date_order = models.DateTimeField(auto_now_add=True)
    complete = models.BooleanField(default=False, null=True, blank=False)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)

    # Snapshot khuyến mãi tại thời điểm áp mã (promotion thuộc promotion-service).
    promotion_id = models.BigIntegerField(null=True, blank=True)
    promotion_code = models.CharField(max_length=20, null=True, blank=True)
    promotion_name = models.CharField(max_length=100, null=True, blank=True)
    promotion_discount_type = models.CharField(max_length=10, null=True, blank=True)
    promotion_apply_type = models.CharField(max_length=10, null=True, blank=True)
    promotion_discount_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    promotion_min_order_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = "GM" + uuid.uuid4().hex[:10].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.id)

    def set_promotion(self, promo):
        self.promotion_id = promo["id"]
        self.promotion_code = promo["code"]
        self.promotion_name = promo["name"]
        self.promotion_discount_type = promo["discount_type"]
        self.promotion_apply_type = promo["apply_type"]
        self.promotion_discount_value = promo["discount_value"]
        self.promotion_min_order_value = promo["min_order_value"]

    def clear_promotion(self):
        for f in ("id", "code", "name", "discount_type", "apply_type", "discount_value", "min_order_value"):
            setattr(self, f"promotion_{f}", None)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product_id = models.BigIntegerField(null=True, blank=True)
    quantity = models.IntegerField(default=0, null=True, blank=True)
    date_added = models.DateTimeField(auto_now_add=True)

    # Snapshot khi đơn hoàn tất: lịch sử đơn hàng không đổi khi sản phẩm đổi giá/đổi tên.
    product_name = models.CharField(max_length=200, blank=True, default="")
    product_slug = models.CharField(max_length=200, blank=True, default="")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["order", "product_id"], name="uniq_order_product")]

    def __str__(self):
        return f"{self.product_id} x {self.quantity}"
