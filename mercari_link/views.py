import csv
import io

from django.contrib import messages
from django.core.management import call_command
from django.http import HttpResponse
from django.shortcuts import redirect, render

from listings.models import Listing
from .forms import MercariCSVImportForm
from .models import MercariLink, StockCheckLog

CSV_HEADERS = ["ItemID", "SKU", "mercari_url", "mercari_sku", "auto_delist_enabled"]

TRUE_VALUES = {"1", "true", "True", "TRUE", "yes", "Yes", "有効", "on"}


def link_list(request):
    links = MercariLink.objects.select_related("listing").all()
    logs = StockCheckLog.objects.select_related("mercari_link__listing")[:50]
    return render(request, "mercari_link/list.html", {"links": links, "logs": logs})


def run_check_now(request):
    if request.method == "POST":
        try:
            call_command("check_mercari_stock")
            messages.success(request, "メルカリ在庫確認を実行しました。")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"実行中にエラー: {exc}")
    return redirect("mercari_link:list")


def export_csv_template(request):
    """既存の紐づけ状況をCSVで出力する。一括編集のひな形として利用できる。"""
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="mercari_links_export.csv"'
    writer = csv.writer(response)
    writer.writerow(CSV_HEADERS)

    linked_ids = set()
    for link in MercariLink.objects.select_related("listing").all():
        linked_ids.add(link.listing_id)
        writer.writerow(
            [
                link.listing.item_id,
                link.listing.sku,
                link.mercari_url,
                link.mercari_sku,
                "1" if link.auto_delist_enabled else "0",
            ]
        )

    # 未紐づけの出品も空欄行として出力し、そのまま埋めてインポートし直せるようにする
    for listing in Listing.objects.exclude(pk__in=linked_ids):
        writer.writerow([listing.item_id, listing.sku, "", "", "1"])

    return response


def import_csv(request):
    """CSVを読み込み、eBay出品(ItemID優先・無ければSKU)にメルカリURLを一括紐づけする。"""
    if request.method == "POST":
        form = MercariCSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            raw = request.FILES["csv_file"].read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(raw))

            created, updated, skipped, not_found = 0, 0, 0, []

            for row in reader:
                item_id = (row.get("ItemID") or "").strip()
                sku = (row.get("SKU") or "").strip()
                mercari_url = (row.get("mercari_url") or "").strip()
                mercari_sku = (row.get("mercari_sku") or "").strip()
                auto_delist_raw = (row.get("auto_delist_enabled") or "1").strip()
                auto_delist = auto_delist_raw in TRUE_VALUES

                if not mercari_url:
                    skipped += 1
                    continue

                listing = None
                if item_id:
                    listing = Listing.objects.filter(item_id=item_id).first()
                if listing is None and sku:
                    listing = Listing.objects.filter(sku=sku).first()

                if listing is None:
                    not_found.append(item_id or sku or "(不明な行)")
                    continue

                _obj, was_created = MercariLink.objects.update_or_create(
                    listing=listing,
                    defaults={
                        "mercari_url": mercari_url,
                        "mercari_sku": mercari_sku,
                        "auto_delist_enabled": auto_delist,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

            msg = f"新規登録 {created}件 / 更新 {updated}件 / 空欄スキップ {skipped}件"
            if not_found:
                msg += f" / 該当出品なし {len(not_found)}件: {', '.join(not_found[:10])}"
                if len(not_found) > 10:
                    msg += " ..."
            messages.success(request, msg)
            return redirect("mercari_link:list")
    else:
        form = MercariCSVImportForm()
    return render(request, "mercari_link/import_csv.html", {"form": form})
