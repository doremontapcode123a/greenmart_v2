from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Promotion
from .serializers import PromotionWriteSerializer, promotion_dict


class PromotionListCreateView(APIView):
    def get(self, request):
        qs = Promotion.objects.all().order_by("id")
        if request.query_params.get("active") in ("1", "true"):
            qs = qs.filter(is_active=True)
        return Response([promotion_dict(p) for p in qs])

    def post(self, request):
        ser = PromotionWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response({"errors": ser.errors}, status=400)
        data = ser.validated_data
        now = timezone.now()
        start = data.pop("start_date", None) or now
        end = data.get("end_date")
        # Quy tắc giữ nguyên bản cũ: chưa tới ngày bắt đầu hoặc đã quá hạn => chưa/không kích hoạt.
        is_active = not (start > now or (end and end < now))
        promo = Promotion.objects.create(is_active=is_active, **data)
        return Response(promotion_dict(promo), status=201)


class PromotionDetailView(APIView):
    def get(self, request, promo_id):
        return Response(promotion_dict(get_object_or_404(Promotion, pk=promo_id)))

    def delete(self, request, promo_id):
        Promotion.objects.filter(pk=promo_id).delete()
        return Response(status=204)
