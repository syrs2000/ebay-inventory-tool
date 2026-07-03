from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    path("", views.listing_list, name="list"),
    path("sync/", views.sync_from_ebay, name="sync"),
    path("export/", views.export_csv, name="export_csv"),
    path("import/", views.import_csv, name="import_csv"),
    path("new/", views.listing_create, name="create"),
    path("<int:pk>/", views.listing_detail, name="detail"),
    path("translate/", views.translate_text, name="translate"),
]
