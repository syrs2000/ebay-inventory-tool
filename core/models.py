from django.db import models


class AppSetting(models.Model):
    """アプリ全体のAPI設定(シングルトン)。設定画面から編集する。

    値が空の場合は .env / 環境変数の値にフォールバックする
    (EbayTradingClient・Gemini連携側で判定)。
    """

    # --- eBay Trading API ---
    ebay_env = models.CharField(
        "eBay環境", max_length=20, blank=True,
        help_text="sandbox または production。空欄なら.envの値を使用",
    )
    ebay_app_id = models.CharField("EBAY_APP_ID", max_length=200, blank=True)
    ebay_dev_id = models.CharField("EBAY_DEV_ID", max_length=200, blank=True)
    ebay_cert_id = models.CharField("EBAY_CERT_ID", max_length=200, blank=True)
    ebay_auth_token = models.TextField("EBAY_AUTH_TOKEN", blank=True)

    # --- Gemini API (翻訳用) ---
    gemini_api_key = models.CharField("Gemini APIキー", max_length=300, blank=True)

    # --- ビジネスポリシー手動登録 (eBayアカウントからの自動取得ができない場合のフォールバック) ---
    # 各要素は {"id": "...", "name": "..."} の辞書のリスト
    manual_payment_profiles = models.JSONField("Payment Policy (手動登録)", default=list, blank=True)
    manual_shipping_profiles = models.JSONField("Shipping Policy (手動登録)", default=list, blank=True)
    manual_return_profiles = models.JSONField("Return Policy (手動登録)", default=list, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "アプリ設定"
        verbose_name_plural = "アプリ設定"

    def __str__(self):
        return "アプリ設定"

    @classmethod
    def load(cls):
        """常に単一行(pk=1)を取得/作成して返す。"""
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
