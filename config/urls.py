from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("listings.urls")),
    path("mercari/", include("mercari_link.urls")),
    path("settings/", include("core.urls")),
]
