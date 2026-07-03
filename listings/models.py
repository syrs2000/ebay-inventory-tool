from django.db import models
from django.urls import reverse


class Listing(models.Model):
    """1件のeBay出品(ItemID)を表す。画面1の一覧テーブルに対応。"""

    STATUS_ACTIVE = "販売中"
    STATUS_CHECK_FAILED = "確認不可"
    STATUS_SOLD_OUT = "売り切れ"
    STATUS_DRAFT = "出品準備中"
    STATUS_ENDED = "終了"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "販売中"),
        (STATUS_CHECK_FAILED, "確認不可"),
        (STATUS_SOLD_OUT, "売り切れ"),
        (STATUS_DRAFT, "出品準備中"),
        (STATUS_ENDED, "終了"),
    ]

    ROUTE_MERCARI = "メルカリ"
    ROUTE_AMAZON = "Amazon"
    ROUTE_OTHER = "その他"
    ROUTE_CHOICES = [
        (ROUTE_MERCARI, "メルカリ"),
        (ROUTE_AMAZON, "Amazon"),
        (ROUTE_OTHER, "その他"),
    ]

    # --- eBay 基本情報 ---
    item_id = models.CharField(
        "ItemID", max_length=32, unique=True, db_index=True, null=True, blank=True
    )
    url = models.URLField("URL", max_length=500, blank=True)
    sku = models.CharField("SKU", max_length=100, blank=True, db_index=True)
    custom_label = models.CharField("カスタムラベル", max_length=100, blank=True)

    title_ja = models.CharField("タイトル(日本語)", max_length=300, blank=True)
    title_en = models.CharField("タイトル(英語)", max_length=300, blank=True)

    currency = models.CharField("通貨", max_length=10, default="USD")
    price = models.DecimalField("販売価格", max_digits=12, decimal_places=2, default=0)
    best_offer = models.DecimalField(
        "Best Offer", max_digits=12, decimal_places=2, null=True, blank=True
    )
    shipping = models.DecimalField("送料", max_digits=12, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField("quantity", default=1)
    watch_count = models.PositiveIntegerField("watch", default=0)

    status = models.CharField(
        "ステータス", max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    route = models.CharField(
        "ルート", max_length=20, choices=ROUTE_CHOICES, default=ROUTE_OTHER
    )
    result_note = models.CharField("結果", max_length=200, blank=True)

    # --- カテゴリ / 商品状態 ---
    category_id = models.CharField("CategoryID", max_length=32, blank=True)
    category_name = models.CharField("Category Name", max_length=200, blank=True)
    condition_id = models.CharField("ConditionID", max_length=16, blank=True)
    condition_description = models.TextField("状態説明", blank=True)

    brand = models.CharField("Brand", max_length=200, blank=True)
    upc = models.CharField("UPC", max_length=64, blank=True)
    mpn = models.CharField("MPN", max_length=64, blank=True)

    # --- ビジネスポリシー (eBayアカウントから取得したPayment/Shipping/Returnポリシー) ---
    payment_profile_id = models.CharField("Payment Policy ID", max_length=32, blank=True)
    payment_profile_name = models.CharField("Payment Policy名", max_length=200, blank=True)
    shipping_profile_id = models.CharField("Shipping Policy ID", max_length=32, blank=True)
    shipping_profile_name = models.CharField("Shipping Policy名", max_length=200, blank=True)
    return_profile_id = models.CharField("Return Policy ID", max_length=32, blank=True)
    return_profile_name = models.CharField("Return Policy名", max_length=200, blank=True)

    # --- Item Specifics: [{"name": "...", "value": "..."}] ---
    item_specifics = models.JSONField("Item Specifics", default=list, blank=True)

    # --- 画像 (URLの配列) ---
    image_urls = models.JSONField("画像URL", default=list, blank=True)

    description_ja = models.TextField("詳細説明(日本語)", blank=True)
    description_html = models.TextField("HTML(英語)", blank=True)

    # --- 仕入れ元 / 追加SKU情報 ---
    supply_url = models.URLField("仕入れ元URL", max_length=500, blank=True)
    supply_price_cap = models.DecimalField(
        "price上限", max_digits=12, decimal_places=2, null=True, blank=True
    )
    supply_memo = models.CharField("メモ", max_length=300, blank=True)
    additional_skus = models.JSONField("追加SKU", default=list, blank=True)  # up to 5

    # --- 利益計算用 ---
    cost_price = models.DecimalField(
        "仕入価格", max_digits=12, decimal_places=2, null=True, blank=True
    )
    fee_percent = models.DecimalField(
        "手数料(%)", max_digits=5, decimal_places=2, default=20
    )
    fx_rate = models.DecimalField(
        "為替", max_digits=8, decimal_places=2, null=True, blank=True
    )
    other_cost = models.DecimalField(
        "送料等", max_digits=12, decimal_places=2, default=0
    )

    is_active = models.BooleanField("出品中", default=True)
    last_synced_at = models.DateTimeField("最終取得日時", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "出品"
        verbose_name_plural = "出品一覧"

    def __str__(self):
        return f"{self.item_id} {self.title_ja or self.title_en}"

    def get_absolute_url(self):
        return reverse("listings:detail", args=[self.pk])

    @property
    def profit_estimate(self):
        """簡易利益計算: 販売価格*為替 - 仕入価格 - 手数料 - 送料等"""
        if not self.fx_rate or self.cost_price is None:
            return None
        revenue_jpy = float(self.price) * float(self.fx_rate)
        fee = revenue_jpy * float(self.fee_percent) / 100
        return round(revenue_jpy - fee - float(self.cost_price) - float(self.other_cost), 2)


class SyncLog(models.Model):
    """eBay取得(GetMyeBaySelling等)の実行履歴。"""

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    fetched_count = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=False)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Sync @ {self.started_at:%Y-%m-%d %H:%M} ({'OK' if self.success else 'NG'})"
