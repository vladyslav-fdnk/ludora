from hmac import compare_digest

from django.conf import settings
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import (
    CreateAPIView,
    RetrieveAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    EmailTokenObtainPairSerializer,
    RegisterSerializer,
    TelegramAuthenticationResponseSerializer,
    TelegramAuthenticationSerializer,
    UserSerializer,
)

User = get_user_model()


class RegisterAPIView(CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer


class MeAPIView(RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [
        IsAuthenticated,
    ]

    def get_object(self):
        return self.request.user


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class TelegramAuthenticationAPIView(APIView):
    authentication_classes = []

    @extend_schema(
        request=TelegramAuthenticationSerializer,
        responses={200: TelegramAuthenticationResponseSerializer},
    )
    def post(self, request):
        expected = settings.BOT_INTERNAL_SECRET
        supplied = request.headers.get("X-Bot-Internal-Secret", "")
        if not expected or not compare_digest(supplied, expected):
            return Response(
                {"detail": "Bot authentication failed."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = TelegramAuthenticationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )
