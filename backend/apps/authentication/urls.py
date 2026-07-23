from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
)

from .views import MeAPIView, RegisterAPIView

urlpatterns = [
    path(
        "register/",
        RegisterAPIView.as_view(),
        name="register",
    ),
    path(
        "login/",
        TokenObtainPairView.as_view(),
        name="login",
    ),
    path(
        "me/",
        MeAPIView.as_view(),
        name="me",
    ),
]
