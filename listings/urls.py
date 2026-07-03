from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    path("", views.listing_list, name="list"),
    path("sync/", views.sync_from_ebay, name="sync"),
    path("fetch/", views.fetch_by_item_id, name="fetch_by_item_id"),
    path("fx-rate/", views.fx_rate_lookup, name="fx_rate"),
    path("export/", views.export_csv, name="export_csv"),
    path("import/", views.import_csv, name="import_csv"),
    path("new/", views.listing_create, name="create"),
    path("<int:pk>/", views.listing_detail, name="detail"),
    path("<int:pk>/preview/", views.listing_preview, name="preview"),
    path("<int:pk>/fetch-mercari-images/", views.fetch_mercari_images, name="fetch_mercari_images"),
    path("<int:pk>/fetch-mercari-description/", views.fetch_mercari_description, name="fetch_mercari_description"),
    path("translate/", views.translate_text, name="translate"),
]
