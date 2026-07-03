from django.contrib import admin

from .models import MercariLink, StockCheckLog


@admin.register(MercariLink)
class MercariLinkAdmin(admin.ModelAdmin):
    list_display = (
        "listing", "mercari_url", "last_stock_status",
        "last_checked_at", "auto_delist_enabled",
    )
    list_filter = ("last_stock_status", "auto_delist_enabled")
    search_fields = ("listing__item_id", "listing__sku", "mercari_url")


@admin.register(StockCheckLog)
class StockCheckLogAdmin(admin.ModelAdmin):
    list_display = ("mercari_link", "checked_at", "status", "action_taken")
    list_filter = ("status",)
