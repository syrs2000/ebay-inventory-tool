import csv
import io

from django.contrib import messages
from django.core.management import call_command
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from mercari_link.models import MercariLink
from .forms import CSVImportForm, ListingForm
from .models import Listing
from .services.ebay_client import EbayApiError, EbayTradingClient

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
            mercari_sku = request.POST.get("mercari_sku", "").strip()
            auto_delist = request.POST.get("auto_delist_enabled") == "on"
            if mercari_url:
                MercariLink.objects.update_or_create(
                    listing=listing,
                    defaults={
                        "mercari_url": mercari_url,
                        "mercari_sku": mercari_sku,
                        "auto_delist_enabled": auto_delist,
                    },
                )
            elif mercari_link:
                mercari_link.delete()

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

    context = {
        "listing": listing,
        "form": form,
        "mercari_link": mercari_link,
        "image_slots": image_slots,
        "sku_slots": sku_slots,
    }
    return render(request, "listings/detail.html", context)


def listing_create(request):
    listing = Listing(status=Listing.STATUS_DRAFT, is_active=False)
    listing.save()
    return redirect(reverse("listings:detail", args=[listing.pk]))


def translate_text(request):
    """詳細説明の日→英 簡易翻訳(deep_translator)。 画面3の「翻訳」ボタン用。"""
    if request.method != "POST":
        return HttpResponse(status=405)
    text = request.POST.get("text", "")
    if not text:
        return HttpResponse("")
    try:
        from deep_translator import GoogleTranslator

        translated = GoogleTranslator(source="ja", target="en").translate(text)
    except Exception as exc:  # noqa: BLE001
        return HttpResponse(f"[翻訳エラー: {exc}]", status=200)
    return HttpResponse(translated)
