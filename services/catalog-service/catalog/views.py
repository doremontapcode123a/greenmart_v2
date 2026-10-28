from django.shortcuts import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Product, Review
from .serializers import ProductWriteSerializer, category_dict, product_dict, review_dict

ALLOWED_ORDERING = {"id", "-id", "created_at", "-created_at", "name", "-name"}


class CategoryListView(APIView):
    def get(self, request):
        return Response([category_dict(c) for c in Category.objects.all().order_by("id")])


class ProductListCreateView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        p = request.query_params
        qs = Product.objects.select_related("category")
        if p.get("featured") in ("1", "true"):
            qs = qs.filter(is_featured=True)
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("q"):
            qs = qs.filter(name__icontains=p["q"])
        if p.get("ids"):
            try:
                qs = qs.filter(pk__in=[int(i) for i in p["ids"].split(",") if i.strip()])
            except ValueError:
                return Response({"error": "invalid_ids"}, status=400)
        ordering = p.get("ordering", "id")
        qs = qs.order_by(ordering if ordering in ALLOWED_ORDERING else "id")
        return Response([product_dict(x) for x in qs])

    def post(self, request):
        ser = ProductWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response({"errors": ser.errors}, status=400)
        product = ser.save()
        return Response(product_dict(product), status=201)


class ProductDetailView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, slug):
        product = get_object_or_404(Product.objects.select_related("category"), slug=slug)
        data = product_dict(product, with_review_count=True)
        top = product.reviews.filter(parent__isnull=True).order_by("-created_at", "-id")
        data["reviews"] = [review_dict(r) for r in top]
        return Response(data)

    def put(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        # Không gửi ảnh mới => giữ ảnh cũ (ProductWriteSerializer: image required=False).
        ser = ProductWriteSerializer(product, data=request.data, partial=True)
        if not ser.is_valid():
            return Response({"errors": ser.errors}, status=400)
        product = ser.save()
        return Response(product_dict(product))


class ProductHideView(APIView):
    """'Xóa' sản phẩm = ẩn + về tồn kho 0 (không xóa dữ liệu) – như bản monolith."""

    def post(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        product.status = "hidden"
        product.stock = 0
        product.save()
        return Response(product_dict(product))


def _clean_user(request):
    try:
        return int(request.data.get("user_id")), (request.data.get("username") or "")[:150]
    except (TypeError, ValueError):
        return None, ""


class ProductReviewCreateView(APIView):
    def post(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        user_id, username = _clean_user(request)
        if user_id is None:
            return Response({"error": "user_required"}, status=400)
        try:
            rating = int(request.data.get("rating", 0))
        except (TypeError, ValueError):
            rating = 0
        comment = (request.data.get("comment") or "").strip()
        if rating < 1 or rating > 5:
            return Response({"error": "invalid_rating"}, status=400)
        if not comment:
            return Response({"error": "empty_comment"}, status=400)
        review = Review.objects.create(product=product, user_id=user_id, username=username,
                                       rating=rating, comment=comment)
        return Response(review_dict(review), status=201)


class ReviewReplyView(APIView):
    def post(self, request, review_id):
        parent = get_object_or_404(Review.objects.select_related("product"), pk=review_id)
        user_id, username = _clean_user(request)
        if user_id is None:
            return Response({"error": "user_required"}, status=400)
        content = request.data.get("content") or ""
        if not content:
            return Response({"error": "empty_comment", "product_slug": parent.product.slug}, status=400)
        reply = Review.objects.create(product=parent.product, user_id=user_id, username=username,
                                      comment=content, parent=parent)
        data = review_dict(reply, with_replies=False)
        data["product_slug"] = parent.product.slug
        return Response(data, status=201)


class StatsView(APIView):
    def get(self, request):
        return Response({"product_count": Product.objects.count(), "category_count": Category.objects.count()})
