import re

from django.contrib.auth import authenticate
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import User, update_last_login
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile


def profile_dict(profile):
    if profile is None:
        return None
    return {"full_name": profile.full_name, "phone": profile.phone, "address": profile.address}


def user_dict(user, with_profile=False):
    data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "is_active": user.is_active,
        "date_joined": user.date_joined,
    }
    if with_profile:
        try:
            data["profile"] = profile_dict(user.profile)
        except UserProfile.DoesNotExist:
            data["profile"] = None
    return data


def _get_user_or_none(user_id):
    return User.objects.filter(pk=user_id).first()


class LoginView(APIView):
    """POST {username, password} -> user | 401."""

    def post(self, request):
        username = request.data.get("username") or ""
        password = request.data.get("password") or ""
        user = authenticate(username=username, password=password)
        if user is None:
            return Response({"error": "invalid_credentials"}, status=401)
        update_last_login(None, user)
        return Response(user_dict(user))


class RegisterView(APIView):
    """POST {username, email, password}. Thứ tự kiểm tra giữ nguyên như bản monolith."""

    def post(self, request):
        username = request.data.get("username") or ""
        email = request.data.get("email") or ""
        password = request.data.get("password") or ""

        if User.objects.filter(email=email).exists():
            return Response({"error": "email_exists"}, status=409)
        if User.objects.filter(username=username).exists():
            return Response({"error": "username_exists"}, status=409)
        if not re.match(r"^[a-zA-Z0-9_]+$", username):
            return Response({"error": "invalid_username"}, status=400)
        if not re.match(r"^[\x00-\x7F]+$", password) or " " in password:
            return Response({"error": "invalid_password"}, status=400)

        user = User.objects.create_user(username=username, email=email, password=password)
        return Response(user_dict(user), status=201)


class UserListView(APIView):
    """GET ?ids=1,2,3&include=profile -> danh sách (mặc định mới nhất trước)."""

    def get(self, request):
        qs = User.objects.all().order_by("-date_joined")
        ids = request.query_params.get("ids")
        if ids:
            try:
                qs = qs.filter(pk__in=[int(i) for i in ids.split(",") if i.strip()])
            except ValueError:
                return Response({"error": "invalid_ids"}, status=400)
        with_profile = request.query_params.get("include") == "profile"
        if with_profile:
            qs = qs.select_related("profile")
        return Response([user_dict(u, with_profile) for u in qs])


class UserDetailView(APIView):
    def get(self, request, user_id):
        user = _get_user_or_none(user_id)
        if user is None:
            return Response({"error": "not_found"}, status=404)
        return Response(user_dict(user, with_profile=request.query_params.get("include") == "profile"))


class UserToggleActiveView(APIView):
    def post(self, request, user_id):
        user = _get_user_or_none(user_id)
        if user is None:
            return Response({"error": "not_found"}, status=404)
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        return Response(user_dict(user))


class ProfileView(APIView):
    """GET (get_or_create) / PUT {full_name, phone, address}."""

    def _profile(self, user_id):
        user = _get_user_or_none(user_id)
        if user is None:
            return None
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile

    def get(self, request, user_id):
        profile = self._profile(user_id)
        if profile is None:
            return Response({"error": "not_found"}, status=404)
        return Response(profile_dict(profile))

    def put(self, request, user_id):
        profile = self._profile(user_id)
        if profile is None:
            return Response({"error": "not_found"}, status=404)
        profile.full_name = (request.data.get("full_name") or "")[:100]
        profile.phone = (request.data.get("phone") or "")[:15]
        profile.address = (request.data.get("address") or "")[:100]
        profile.save()
        return Response(profile_dict(profile))


class StatsView(APIView):
    def get(self, request):
        return Response({"user_count": User.objects.count()})


class PasswordResetRequestView(APIView):
    """POST {email}. Luôn trả 202 (không lộ email nào tồn tại), giống PasswordResetView của Django."""

    def post(self, request):
        form = PasswordResetForm({"email": request.data.get("email") or ""})
        if form.is_valid():
            form.save(
                domain_override=settings.PUBLIC_HOST,
                use_https=settings.PUBLIC_SCHEME == "https",
                from_email=settings.DEFAULT_FROM_EMAIL,
                request=None,
            )
        return Response({"status": "accepted"}, status=202)


def _user_from_uid(uidb64):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


class PasswordResetValidateView(APIView):
    def post(self, request):
        user = _user_from_uid(request.data.get("uid") or "")
        valid = bool(user and default_token_generator.check_token(user, request.data.get("token") or ""))
        return Response({"valid": valid})


class PasswordResetConfirmView(APIView):
    def post(self, request):
        user = _user_from_uid(request.data.get("uid") or "")
        if not (user and default_token_generator.check_token(user, request.data.get("token") or "")):
            return Response({"error": "invalid_link"}, status=400)
        form = SetPasswordForm(user, {
            "new_password1": request.data.get("new_password1") or "",
            "new_password2": request.data.get("new_password2") or "",
        })
        if not form.is_valid():
            messages = [m for errs in form.errors.values() for m in errs]
            return Response({"error": "invalid_password", "messages": messages}, status=400)
        form.save()
        return Response({"status": "ok"})
