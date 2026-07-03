from django.urls import path

from . import views

app_name = "mercari_link"

urlpatterns = [
    path("", views.link_list, name="list"),
    path("check-now/", views.run_check_now, name="check_now"),
    path("export/", views.export_csv_template, name="export_csv"),
    path("import/", views.import_csv, name="import_csv"),
]
