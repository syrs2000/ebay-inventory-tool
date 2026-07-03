import csv
import io
import logging

from django.contrib import messages
from django.core.cache import cache
from django.core.management import call_command
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from mercari_link.models import MercariLink
from mercari_link.services.mercari_checker import (
    MercariCheckError,
    extract_mercari_id,
    extract_product_description,
    extract_product_images,
)
from .forms import CSVImportForm, ListingForm
from .models import Listing
from .services.ebay_client import EbayApiError, EbayTradingClient
from .services.fx_client import FxRateError, get_usd_jpy_rate

SELLER_PROFILES_CACHE_KEY = "ebay_seller_profiles"
SELLER_PROFILES_CACHE_TTL = 3600  # 1時間


def _merge_manual_profiles(profiles, manual):
    """自動取得結果に、設定画面で手動登録されたポリシーをID重複なしで追加する。"""
    merged = {}
    for key in ("payment", "shipping", "return"):
        existing_ids = {p["id"] for p in profiles.get(key, [])}
        extra = [
            p for p in manual.get(key, [])
            if p.get("id") and p["id"] not in existing_ids
        ]
        merged[key] = list(profiles.get(key, [])) + extra
    return merged


def _get_seller_profiles(force_refresh=False):
    """Business Policies一覧をキャッシュ付きで取得する。
    設定画面で手動登録されたポリシーがあれば、自動取得結果にマージする。
    取得失敗時は (手動登録分のみ, エラーメッセージ) を返す。"""
    from core.models import AppSetting

    setting = AppSetting.load()
    manual = {
        "payment": setting.manual_payment_profiles or [],
        "shipping": setting.manual_shipping_profiles or [],
        "return": setting.manual_return_profiles or [],
    }

    if not force_refresh:
        cached = cache.get(SELLER_PROFILES_CACHE_KEY)
        if cached is not None:
            return _merge_manual_profiles(cached, manual), None
    try:
        client = EbayTradingClient()
        profiles = client.get_seller_profiles()
    except EbayApiError as exc:
        empty = {"payment": [], "shipping": [], "return": []}
        return _merge_manual_profiles(empty, manual), f"ビジネスポリシー取得エラー: {exc}"
    except Exception as exc:  # noqa: BLE001
        empty = {"payment": [], "shipping": [], "return": []}
        return _merge_manual_profiles(empty, manual), f"ビジネスポリシー取得中にエラーが発生しました: {exc}"
    cache.set(SELLER_PROFILES_CACHE_KEY, profiles, SELLER_PROFILES_CACHE_TTL)
    return _merge_manual_profiles(profiles, manual), None


def _profile_name(profiles_list, profile_id):
    for p in profiles_list:
        if p["id"] == profile_id:
            return p["name"]
    return ""

CSV_FIELDS = [
    "item_id", "url", "result_note", "status", "route",
    "title_ja", "sku", "currency", "price", "shipping",
    "watch_count", "quantity",
]

CSV_HEADERS_JA = [
    "ItemID", "URL", "結果", "ステータス", "ルート",
    "title", "SKU", "通貨", "販売価格", "送料", "watch", "quantity",
]


def listing_list(request):
    qs = Listing.objects.all()

    filter_key = request.GET.get("filter", "all")
    if filter_key == "no_stock":
        qs = qs.filter(quantity=0)
    elif filter_key == "check_failed":
        qs = qs.filter(status=Listing.STATUS_CHECK_FAILED)

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(sku__icontains=q) | qs.filter(item_id__icontains=q)

    try:
        start = max(int(request.GET.get("from", 1)), 1)
    except ValueError:
        start = 1
    try:
        end = max(int(request.GET.get("to", 200)), start)
    except ValueError:
        end = start + 199

    total_count = qs.count()
    page_qs = qs[start - 1 : end]

    context = {
        "listings": page_qs,
        "filter_key": filter_key,
        "q": q,
        "from": start,
        "to": end,
        "total_count": total_count,
    }
    return render(request, "listings/list.html", context)


def sync_from_ebay(request):
    if request.method == "POST":
        try:
            call_command("fetch_ebay_listings")
            messages.success(request, "eBayから出品データを取得しました。")
        except EbayApiError as exc:
            messages.error(request, f"eBay取得エラー: {exc}")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"取得中にエラーが発生しました: {exc}")
    return redirect("listings:list")


def fetch_by_item_id(request):
    """出品タグの「ItemIDから取得」ボタン用。eBayのGetItemで単一出品の詳細を取得し、
    既存Listingがあれば上書き、なければ新規作成する。"""
    if request.method != "POST":
        return redirect("listings:list")

    item_id = request.POST.get("item_id", "").strip()
    if not item_id:
        messages.error(request, "ItemIDを入力してください。")
        return redirect("listings:list")

    client = EbayTradingClient()
    try:
        data = client.get_item(item_id)
    except EbayApiError as exc:
        messages.error(request, f"eBay取得エラー: {exc}")
        return redirect("listings:list")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"取得中にエラーが発生しました: {exc}")
        return redirect("listings:list")

    listing, created = Listing.objects.update_or_create(
        item_id=data.item_id,
        defaults={
            "url": data.listing_url,
            "sku": data.sku,
            "custom_label": data.custom_label,
            "title_en": data.title,
            "currency": data.currency,
            "price": data.price,
            "quantity": data.quantity_available,
            "watch_count": data.watch_count,
            "status": Listing.STATUS_ACTIVE,
            "is_active": True,
            "last_synced_at": timezone.now(),
            "description_html": data.description_html,
            "category_id": data.category_id,
            "category_name": data.category_name,
            "condition_id": data.condition_id,
            "condition_description": data.condition_description,
            "brand": data.brand,
            "upc": data.upc,
            "mpn": data.mpn,
            "item_specifics": data.item_specifics,
            "image_urls": data.image_urls,
        },
    )
    verb = "取得して新規登録" if created else "取得して更新"
    messages.success(request, f"ItemID {data.item_id} の詳細情報を{verb}しました。")
    return redirect(reverse("listings:detail", args=[listing.pk]))


def fx_rate_lookup(request):
    """為替(USD->JPY)の自動取得ボタン用。JSONでレートを返す。"""
    if request.method != "POST":
        return JsonResponse({"error": "POSTで呼び出してください。"}, status=405)
    try:
        rate = get_usd_jpy_rate()
    except FxRateError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"rate": str(rate)})


def fetch_mercari_images(request, pk):
    """出品編集画面の「メルカリから画像取得」ボタン用 (Ajax/JSON)。

    フォーム未保存でも、画面上のメルカリURL入力欄の値をそのまま受け取って
    Playwrightで画像を取得できるようにする(保存済みリンクがあればそれを既定値として使う)。
    取得できた画像はDBにも反映しつつ、JSONで返して画面側で即座に入力欄へ反映する。
    """
    listing = get_object_or_404(Listing, pk=pk)
    if request.method != "POST":
        return JsonResponse({"error": "POSTで呼び出してください。"}, status=405)

    mercari_url = request.POST.get("mercari_url", "").strip()
    if not mercari_url:
        mercari_link = getattr(listing, "mercari_link", None)
        mercari_url = mercari_link.mercari_url if mercari_link else ""
    if not mercari_url:
        return JsonResponse({"error": "メルカリURLを入力してください。"}, status=400)

    try:
        images = extract_product_images(mercari_url)
    except MercariCheckError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": f"取得中にエラーが発生しました: {exc}"}, status=500)

    images = images[:10]
    listing.image_urls = images
    listing.save(update_fields=["image_urls"])
    return JsonResponse({"images": images})


def fetch_mercari_description(request, pk):
    """出品編集画面の「メルカリから説明文取得」ボタン用 (Ajax/JSON)。

    フォーム未保存でも、画面上のメルカリURL入力欄の値をそのまま受け取って
    Playwrightで商品説明文を取得し、日本語説明欄(description_ja)に反映する。
    """
    listing = get_object_or_404(Listing, pk=pk)
    if request.method != "POST":
        return JsonResponse({"error": "POSTで呼び出してください。"}, status=405)

    mercari_url = request.POST.get("mercari_url", "").strip()
    if not mercari_url:
        mercari_link = getattr(listing, "mercari_link", None)
        mercari_url = mercari_link.mercari_url if mercari_link else ""
    if not mercari_url:
        return JsonResponse({"error": "メルカリURLを入力してください。"}, status=400)

    try:
        description = extract_product_description(mercari_url)
    except MercariCheckError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": f"取得中にエラーが発生しました: {exc}"}, status=500)

    listing.description_ja = description
    listing.save(update_fields=["description_ja"])
    return JsonResponse({"description": description})


def listing_preview(request, pk):
    """出品内容を別ウィンドウ/タブで表示するための単独プレビューページ。"""
    listing = get_object_or_404(Listing, pk=pk)
    return render(request, "listings/preview.html", {"listing": listing})


def export_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="listings_export.csv"'
    writer = csv.writer(response)
    writer.writerow(CSV_HEADERS_JA)
    for listing in Listing.objects.all():
        writer.writerow(
            [
                listing.item_id, listing.url, listing.result_note, listing.status,
                listing.route, listing.title_ja or listing.title_en, listing.sku,
                listing.currency, listing.price, listing.shipping,
                listing.watch_count, listing.quantity,
            ]
        )
    return response


def import_csv(request):
    if request.method == "POST":
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            raw = request.FILES["csv_file"].read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(raw))
            count = 0
            for row in reader:
                item_id = row.get("ItemID") or row.get("item_id")
                if not item_id:
                    continue
                Listing.objects.update_or_create(
                    item_id=item_id,
                    defaults={
                        "url": row.get("URL", ""),
                        "sku": row.get("SKU", ""),
                        "title_ja": row.get("title", ""),
                        "currency": row.get("通貨", "USD") or "USD",
                        "price": row.get("販売価格") or 0,
                        "shipping": row.get("送料") or 0,
                        "watch_count": row.get("watch") or 0,
                        "quantity": row.get("quantity") or 0,
                        "status": row.get("ステータス", Listing.STATUS_DRAFT),
                        "route": row.get("ルート", Listing.ROUTE_OTHER) or Listing.ROUTE_OTHER,
                    },
                )
                count += 1
            messages.success(request, f"{count}件をCSVから取込みました。")
            return redirect("listings:list")
    else:
        form = CSVImportForm()
    return render(request, "listings/import_csv.html", {"form": form})


def listing_detail(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    mercari_link = getattr(listing, "mercari_link", None)

    if request.method == "POST":
        form = ListingForm(request.POST, instance=listing)
        if form.is_valid():
            listing = form.save(commit=False)

            names = request.POST.getlist("specific_name")
            values = request.POST.getlist("specific_value")
            listing.item_specifics = [
                {"name": n, "value": v} for n, v in zip(names, values) if n.strip()
            ]

            image_urls = [u for u in request.POST.getlist("image_url") if u.strip()]
            listing.image_urls = image_urls

            additional_skus = [
                s for s in request.POST.getlist("additional_sku") if s.strip()
            ]
            listing.additional_skus = additional_skus

            listing.save()

            mercari_url = request.POST.get("mercari_url", "").strip()
            auto_delist = request.POST.get("auto_delist_enabled") == "on"
            if mercari_url:
                # メルカリSKUはURLに含まれる "m+数字" のIDをそのまま使う
                derived_sku = extract_mercari_id(mercari_url)
                MercariLink.objects.update_or_create(
                    listing=listing,
                    defaults={
                        "mercari_url": mercari_url,
                        "mercari_sku": derived_sku or request.POST.get("mercari_sku", "").strip(),
                        "auto_delist_enabled": auto_delist,
                    },
                )
            elif mercari_link:
                mercari_link.delete()

            # ビジネスポリシー (Payment/Shipping/Return) の選択を反映
            profiles, _profiles_error = _get_seller_profiles()
            payment_id = request.POST.get("payment_profile_id", "").strip()
            shipping_id = request.POST.get("shipping_profile_id", "").strip()
            return_id = request.POST.get("return_profile_id", "").strip()
            listing.payment_profile_id = payment_id
            listing.payment_profile_name = _profile_name(profiles["payment"], payment_id)
            listing.shipping_profile_id = shipping_id
            listing.shipping_profile_name = _profile_name(profiles["shipping"], shipping_id)
            listing.return_profile_id = return_id
            listing.return_profile_name = _profile_name(profiles["return"], return_id)
            listing.save(
                update_fields=[
                    "payment_profile_id", "payment_profile_name",
                    "shipping_profile_id", "shipping_profile_name",
                    "return_profile_id", "return_profile_name",
                ]
            )

            if "save_and_push" in request.POST:
                client = EbayTradingClient()
                try:
                    if listing.item_id:
                        client.revise_fixed_price_item(listing)
                        messages.success(request, "eBayへ改訂内容を反映しました。")
                    else:
                        new_item_id = client.add_fixed_price_item(listing)
                        listing.item_id = new_item_id
                        listing.status = Listing.STATUS_ACTIVE
                        listing.is_active = True
                        listing.save(update_fields=["item_id", "status", "is_active"])
                        messages.success(request, f"eBayへ新規出品しました (ItemID: {new_item_id})")
                except EbayApiError as exc:
                    messages.error(request, f"eBay出品エラー: {exc}")
            else:
                messages.success(request, "保存しました。")

            return redirect(reverse("listings:detail", args=[listing.pk]))
    else:
        form = ListingForm(instance=listing)

    image_slots = (listing.image_urls or [])[:10]
    image_slots += [""] * (10 - len(image_slots))

    sku_slots = (listing.additional_skus or [])[:5]
    sku_slots += [""] * (5 - len(sku_slots))

    force_refresh = request.GET.get("refresh_profiles") == "1"
    profiles, profiles_error = _get_seller_profiles(force_refresh=force_refresh)

    context = {
        "listing": listing,
        "form": form,
        "mercari_link": mercari_link,
        "image_slots": image_slots,
        "sku_slots": sku_slots,
        "payment_profiles": profiles["payment"],
        "shipping_profiles": profiles["shipping"],
        "return_profiles": profiles["return"],
        "profiles_error": profiles_error,
    }
    return render(request, "listings/detail.html", context)


def listing_create(request):
    # item_id は未出品ドラフトの間は空(NULL)。unique制約のため空文字ではなくNoneにする
    # (空文字だと2件目以降のドラフト作成でUNIQUE制約違反になる)。
    listing = Listing(status=Listing.STATUS_DRAFT, is_active=False, item_id=None)
    listing.save()
    return redirect(reverse("listings:detail", args=[listing.pk]))


def translate_text(request):
    """詳細説明の日→英 翻訳。画面3の「翻訳」ボタン用。

    設定画面でGemini APIキーが登録されていればGeminiで翻訳する。
    未設定、またはGemini呼び出しに失敗した場合はdeep_translator(Google翻訳)にフォールバックする。
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    text = request.POST.get("text", "")
    if not text:
        return HttpResponse("")

    from .services import gemini_client

    if gemini_client.is_configured():
        try:
            return HttpResponse(gemini_client.translate_ja_to_en(text))
        except Exception as exc:  # noqa: BLE001 — Geminiのどんな失敗でも従来の翻訳へフォールバック
            logging.getLogger(__name__).warning("Gemini translation failed, falling back: %s", exc)

    try:
        from deep_translator import GoogleTranslator

        translated = GoogleTranslator(source="ja", target="en").translate(text)
    except Exception as exc:  # noqa: BLE001
        return HttpResponse(f"[翻訳エラー: {exc}]", status=200)
    return HttpResponse(translated)
