from django import forms

from .models import Listing


class ListingForm(forms.ModelForm):
    """画面3(出品編集)の主要スカラー項目。Item Specifics/画像/追加SKUはビュー側でJSON処理する。"""

    class Meta:
        model = Listing
        fields = [
            "title_ja",
            "title_en",
            "category_id",
            "category_name",
            "condition_id",
            "condition_description",
            "brand",
            "upc",
            "mpn",
            "currency",
            "price",
            "best_offer",
            "quantity",
            "custom_label",
            "sku",
            "description_ja",
            "description_html",
            "supply_url",
            "supply_price_cap",
            "supply_memo",
            "cost_price",
            "fee_percent",
            "fx_rate",
            "other_cost",
        ]
        widgets = {
            "condition_description": forms.Textarea(attrs={"rows": 2}),
            "description_ja": forms.Textarea(attrs={"rows": 6}),
            "description_html": forms.Textarea(attrs={"rows": 6}),
        }


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(label="CSVファイル")
