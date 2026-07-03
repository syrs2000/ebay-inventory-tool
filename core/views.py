from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect, render

from .models import AppSetting


def _collect_profiles(request, prefix):
    ids = request.POST.getlist(f"{prefix}_id")
    names = request.POST.getlist(f"{prefix}_name")
    return [
        {"id": i.strip(), "name": n.strip()}
        for i, n in zip(ids, names)
        if i.strip()
    ]


def _pad(profiles, n=5):
    profiles = list(profiles or [])
    profiles += [{"id": "", "name": ""}] * (n - len(profiles))
    return profiles[:n]


def settings_view(request):
    """設定タブ。eBay認証情報・Gemini APIキー・ビジネスポリシーの手動登録を
    ブラウザから編集・保存できる画面。値はDB(AppSetting)に保存され、
    空欄の項目は.env側の値にフォールバックする。"""
    setting = AppSetting.load()

    if request.method == "POST":
        setting.ebay_env = request.POST.get("ebay_env", "").strip()
        setting.ebay_app_id = request.POST.get("ebay_app_id", "").strip()
        setting.ebay_dev_id = request.POST.get("ebay_dev_id", "").strip()
        setting.ebay_cert_id = request.POST.get("ebay_cert_id", "").strip()
        setting.ebay_auth_token = request.POST.get("ebay_auth_token", "").strip()
        setting.gemini_api_key = request.POST.get("gemini_api_key", "").strip()

        setting.manual_payment_profiles = _collect_profiles(request, "payment")
        setting.manual_shipping_profiles = _collect_profiles(request, "shipping")
        setting.manual_return_profiles = _collect_profiles(request, "return")

        setting.save()

        # 認証情報/ビジネスポリシーが変わった可能性があるのでキャッシュをクリア
        cache.delete("ebay_seller_profiles")

        messages.success(request, "設定を保存しました。")
        return redirect("core:settings")

    context = {
        "setting": setting,
        "payment_slots": _pad(setting.manual_payment_profiles),
        "shipping_slots": _pad(setting.manual_shipping_profiles),
        "return_slots": _pad(setting.manual_return_profiles),
    }
    return render(request, "core/settings.html", context)
