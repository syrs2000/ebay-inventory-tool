"""
python manage.py fetch_ebay_listings

eBay の GetMyeBaySelling を叩き、アクティブ出品を Listing テーブルに upsert する。
画面1の「START」/「全データ」ボタンに相当する処理。
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from listings.models import Listing, SyncLog
from listings.services.ebay_client import EbayApiError, EbayTradingClient


class Command(BaseCommand):
    help = "eBay GetMyeBaySelling を実行し、出品データを取り込む"

    def add_arguments(self, parser):
        parser.add_argument("--pages", type=int, default=10)

    def handle(self, *args, **options):
        client = EbayTradingClient()
        log = SyncLog.objects.create()
        fetched = 0
        try:
            page = 1
            total_pages = 1
            while page <= total_pages and page <= options["pages"]:
                items, total_pages, total_entries = client.get_my_ebay_selling(page_number=page)
                for data in items:
                    obj, _created = Listing.objects.update_or_create(
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
                        },
                    )
                    fetched += 1
                page += 1

            log.success = True
            log.fetched_count = fetched
            log.message = f"{fetched} 件取り込み完了"
            self.stdout.write(self.style.SUCCESS(log.message))
        except EbayApiError as exc:
            log.success = False
            log.message = str(exc)
            self.stderr.write(self.style.ERROR(str(exc)))
        finally:
            log.finished_at = timezone.now()
            log.save()
