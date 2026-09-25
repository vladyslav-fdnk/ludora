from django.urls import path

from .views import (
    EmailTokenObtainPairView,
    MeAPIView,
    RegisterAPIView,
    TelegramAuthenticationAPIView,
    ThrottledTokenRefreshView,
)

urlpatterns = [
    path(
        "register/",
        RegisterAPIView.as_view(),
        name="register",
    ),
    path(
        "token/",
        EmailTokenObtainPairView.as_view(),
        name="token-obtain-pair",
    ),
    path(
        "token/refresh/",
        ThrottledTokenRefreshView.as_view(),
        name="token-refresh",
    ),
    # Compatibility aliases used by the existing Telegram client.
    path(
        "login/",
        EmailTokenObtainPairView.as_view(),
        name="login",
    ),
    path(
        "refresh/",
        ThrottledTokenRefreshView.as_view(),
        name="refresh",
    ),
    path(
        "me/",
        MeAPIView.as_view(),
        name="me",
    ),
    path(
        "telegram/",
        TelegramAuthenticationAPIView.as_view(),
        name="telegram-authentication",
    ),
]
