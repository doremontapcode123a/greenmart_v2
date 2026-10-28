from rest_framework import serializers

from .models import Promotion


def promotion_dict(p):
    return {
        "id": p.id,
        "user_id": p.user_id,
        "name": p.name,
        "code": p.code,
        "discount_type": p.discount_type,
        "get_discount_type_display": p.get_discount_type_display(),
        "discount_value": str(p.discount_value),
        "apply_type": p.apply_type,
        "get_apply_type_display": p.get_apply_type_display(),
        "product_ids": p.product_ids,
        "category_ids": p.category_ids,
        "start_date": p.start_date,
        "end_date": p.end_date,
        "is_active": p.is_active,
        "min_order_value": str(p.min_order_value),
    }


class PromotionWriteSerializer(serializers.ModelSerializer):
    # start_date là auto_now_add (giống bản cũ: giá trị form bị bỏ qua khi lưu) nhưng vẫn được dùng để tính is_active.
    start_date = serializers.DateTimeField(required=False, allow_null=True)

    class Meta:
        model = Promotion
        fields = ["name", "code", "discount_type", "discount_value", "apply_type",
                  "start_date", "end_date", "min_order_value"]
        extra_kwargs = {"min_order_value": {"required": False}}
