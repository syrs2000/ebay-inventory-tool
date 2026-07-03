from django.contrib import admin

from .models import Listing, SyncLog


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = (
        "item_id", "sku", "title_ja", "status", "route",
        "currency", "price", "quantity", "watch_count", "is_active",
    )
    list_filter = ("status", "route", "is_active", "currency")
    search_fields = ("item_id", "sku", "title_ja", "title_en")


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("started_at", "finished_at", "fetched_count", "success")
