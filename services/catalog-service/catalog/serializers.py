"""Chuyển model -> dict JSON. Tên khóa (get_unit_display, ...) cố ý khớp với thuộc tính mà
template của storefront đang dùng để template không phải sửa."""
from django.utils.text import slugify
from rest_framework import serializers

from .models import Category, Origin, Product, Review


def category_dict(c):
    return {"id": c.id, "name": c.name, "slug": c.slug}


def product_dict(p, with_review_count=False):
    data = {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "category": category_dict(p.category),
        "description": p.description,
        "price": str(p.price),
        "unit": p.unit,
        "get_unit_display": p.get_unit_display(),
        "stock": p.stock,
        "status": p.status,
        "get_status_display": p.get_status_display(),
        "origin": p.origin,
        "get_origin_display": p.get_origin_display() if p.origin else "",
        "image": {"url": p.image.url} if p.image else None,
        "is_featured": p.is_featured,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "user_id": p.user_id,
    }
    if with_review_count:
        data["review_count"] = p.reviews.count()
    return data


def review_dict(r, with_replies=True):
    data = {
        "id": r.id,
        "rating": r.rating,
        "comment": r.comment,
        "created_at": r.created_at,
        "user": {"id": r.user_id, "username": r.username},
        "parent_id": r.parent_id,
    }
    if with_replies:
        data["replies"] = [review_dict(x, with_replies=False) for x in r.replies.all().order_by("id")]
    return data


class ProductWriteSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(source="category", queryset=Category.objects.all())
    origin = serializers.ChoiceField(choices=Origin.choices, required=False, allow_blank=True, allow_null=True)
    image = serializers.ImageField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Product
        fields = ["name", "category_id", "description", "price", "unit", "stock",
                  "status", "origin", "image", "is_featured"]

    def validate_name(self, value):
        # slug chỉ sinh khi tạo mới; đổi tên sản phẩm không đổi slug (giống bản monolith).
        if self.instance is None:
            slug = slugify(value)
            if not slug:
                raise serializers.ValidationError("Tên sản phẩm không hợp lệ.")
            if Product.objects.filter(slug=slug).exists():
                raise serializers.ValidationError("Đã có sản phẩm cùng tên (slug trùng).")
        return value
