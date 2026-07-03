"""
python manage.py check_mercari_stock

紐づけ済みメルカリ商品ページを巡回し、売り切れを検知したら
対応するeBay出品を自動で取り下げる(EndFixedPriceItem)。

Windowsタスクスケジューラや `run_scheduler` コマンドから定期実行する想定。
"""

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from listings.models import Listing
from listings.services.ebay_client import EbayApiError, EbayTradingClient
from mercari_link.models import MercariLink, StockCheckLog
from mercari_link.services.mercari_checker import MercariCheckError, check_stock_status


class Command(BaseCommand):
    help = "メルカリ在庫を確認し、売り切れなら紐づくeBay出品を自動取り下げる"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="eBay側の取り下げは行わず判定のみ実施"
        )
        parser.add_argument(
            "--sleep", type=float, default=2.0, help="商品間のアクセス間隔(秒)"
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        links = MercariLink.objects.filter(auto_delist_enabled=True).select_related("listing")
        ebay_client = EbayTradingClient()

        checked = 0
        delisted = 0

        for link in links:
            checked += 1
            try:
                status = check_stock_status(link.mercari_url)
            except MercariCheckError as exc:
                StockCheckLog.objects.create(
                    mercari_link=link, status="エラー", note=str(exc)
                )
                self.stderr.write(self.style.WARNING(f"{link.mercari_url}: {exc}"))
                time.sleep(options["sleep"])
                continue

            link.last_stock_status = status
            link.last_checked_at = timezone.now()
            link.save(update_fields=["last_stock_status", "last_checked_at"])

            action = ""
            if status == MercariLink.STOCK_SOLD_OUT and link.listing.is_active:
                if dry_run:
                    action = "(dry-run) eBay出品終了スキップ"
                else:
                    try:
                        ebay_client.end_item(link.listing.item_id)
                        link.listing.status = Listing.STATUS_SOLD_OUT
                        link.listing.is_active = False
                        link.listing.save(update_fields=["status", "is_active"])
                        link.delisted_at = timezone.now()
                        link.save(update_fields=["delisted_at"])
                        action = "eBay出品終了"
                        delisted += 1
                    except EbayApiError as exc:
                        action = f"eBay取り下げ失敗: {exc}"

            StockCheckLog.objects.create(
                mercari_link=link, status=status, action_taken=action
            )
            self.stdout.write(f"{link.listing.item_id}: {status} {action}")
            time.sleep(options["sleep"])

        self.stdout.write(
            self.style.SUCCESS(f"確認完了: {checked}件チェック / {delisted}件取り下げ")
        )
