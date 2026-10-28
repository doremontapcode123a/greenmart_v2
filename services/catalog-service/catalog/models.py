from django.db import models
from django.utils.text import slugify


class Origin(models.TextChoices):
    VIETNAM = "VN", "Việt Nam"
    USA = "US", "Mỹ"
    AUSTRALIA = "AU", "Úc"
    JAPAN = "JP", "Nhật Bản"
    KOREA = "KR", "Hàn Quốc"
    THAILAND = "TH", "Thái Lan"
    OTHER = "OT", "Khác"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)  # Rau, Củ, Quả, Trái Cây, Nấm, ...
    slug = models.SlugField(max_length=100, blank=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    UNIT_CHOICES = [
        ("kg", "Kilogram"),
        ("gr", "Gram"),
        ("bó", "Bó"),
        ("túi", "Túi"),
        ("quả", "Quả"),
    ]
    STATUS_CHOICES = [
        ("available", "Còn hàng"),
        ("out_of_stock", "Hết hàng"),
        ("hidden", "Ẩn"),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    description = models.TextField(blank=True, null=True)

    price = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default="kg")
    stock = models.PositiveIntegerField(default=0)  # số lượng tồn kho
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="available")
    origin = models.CharField(max_length=100, choices=Origin.choices, default=Origin.VIETNAM, blank=True, null=True)

    image = models.ImageField(upload_to="products/", blank=True, null=True)

    is_featured = models.BooleanField(default=False)  # Sản phẩm nổi bật
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Trước đây là FK tới auth.User. Nay user thuộc user-service nên chỉ giữ id (không có ràng buộc FK liên DB).
    user_id = models.BigIntegerField(blank=True, null=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    # user thuộc user-service: lưu id + username tại thời điểm viết để hiển thị mà không cần gọi chéo service.
    user_id = models.BigIntegerField(db_index=True)
    username = models.CharField(max_length=150)
    rating = models.IntegerField(default=1)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")

    def __str__(self):
        return f"{self.username} - {self.product.name} ({self.rating}⭐)"

    @property
    def is_parent(self):
        return self.parent_id is None
