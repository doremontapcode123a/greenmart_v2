from django.db import models


class Promotion(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ("money", "Giảm theo số tiền"),
        ("percent", "Giảm theo phần trăm"),
    ]
    APPLY_TYPE_CHOICES = [
        ("product", "Theo sản phẩm"),
        ("category", "Theo danh mục"),
        ("order", "Toàn đơn hàng"),
    ]

    # user / products / categories thuộc service khác => chỉ lưu id, không có FK liên DB.
    user_id = models.BigIntegerField(blank=True, null=True)

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES)
    # Bản cũ khai báo max_digits=100000000: SQLite bỏ qua, nhưng MySQL giới hạn DECIMAL tối đa 65 chữ số nên sẽ lỗi.
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    apply_type = models.CharField(max_length=10, choices=APPLY_TYPE_CHOICES, default="order")

    product_ids = models.JSONField(default=list, blank=True)
    category_ids = models.JSONField(default=list, blank=True)

    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    min_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} ({self.code})"
