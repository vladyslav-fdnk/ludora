from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]

# TODO: include apps.games / apps.users / apps.orders / apps.payments URLs
# once the REST API (Django REST Framework) is introduced.
