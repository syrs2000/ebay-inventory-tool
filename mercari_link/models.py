from django.db import models

from listings.models import Listing


class MercariLink(models.Model):
    """eBay出品(Listing)とメルカリ商品ページを紐づけ、在庫状況を監視する。"""

    STOCK_UNKNOWN = "不明"
    STOCK_IN_STOCK = "在庫あり"
    STOCK_SOLD_OUT = "売り切れ"
    STOCK_CHOICES = [
        (STOCK_UNKNOWN, "不明"),
        (STOCK_IN_STOCK, "在庫あり"),
        (STOCK_SOLD_OUT, "売り切れ"),
    ]

    listing = models.OneToOneField(
        Listing, on_delete=models.CASCADE, related_name="mercari_link"
    )
    mercari_url = models.URLField("メルカリURL", max_length=500)
    mercari_sku = models.CharField("メルカリSKU/管理番号", max_length=100, blank=True)

    last_stock_status = models.CharField(
        "在庫状況", max_length=10, choices=STOCK_CHOICES, default=STOCK_UNKNOWN
    )
    last_checked_at = models.DateTimeField("最終確認日時", null=True, blank=True)

    auto_delist_enabled = models.BooleanField("自動取り下げ有効", default=True)
    delisted_at = models.DateTimeField("取り下げ日時", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "メルカリ紐づけ"
        verbose_name_plural = "メルカリ紐づけ一覧"

    def __str__(self):
        return f"{self.listing.item_id} -> {self.mercari_url}"


class StockCheckLog(models.Model):
    """在庫確認の実行ログ(自動取り下げの監査証跡)。"""

    mercari_link = models.ForeignKey(
        MercariLink, on_delete=models.CASCADE, related_name="logs"
    )
    checked_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField("結果ステータス", max_length=10)
    action_taken = models.CharField(
        "実施アクション", max_length=50, blank=True
    )  # 例: "eBay出品終了"
    note = models.TextField("備考", blank=True)

    class Meta:
        ordering = ["-checked_at"]
        verbose_name = "在庫確認ログ"
        verbose_name_plural = "在庫確認ログ一覧"

    def __str__(self):
        return f"{self.mercari_link} @ {self.checked_at:%Y-%m-%d %H:%M} - {self.status}"
