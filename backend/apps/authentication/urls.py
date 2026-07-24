from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

from .views import EmailTokenObtainPairView, MeAPIView, RegisterAPIView

urlpatterns = [
    path(
        "register/",
        RegisterAPIView.as_view(),
        name="register",
    ),
    path(
        "login/",
        EmailTokenObtainPairView.as_view(),
        name="login",
    ),
    path(
        "refresh/",
        TokenRefreshView.as_view(),
        name="refresh",
    ),
    path(
        "me/",
        MeAPIView.as_view(),
        name="me",
    ),
]
