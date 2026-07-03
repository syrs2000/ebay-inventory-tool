"""
python manage.py run_scheduler

ローカルPCで常時起動しておくためのバックグラウンドスケジューラ。
- 一定間隔でメルカリ在庫を確認し、売り切れのeBay出品を自動取り下げ
- 一定間隔でeBay出品一覧を再取得

runserver とは別プロセスとして常駐させる想定
(例: Windowsタスクスケジューラでログイン時に `python manage.py run_scheduler` を起動)。
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django_apscheduler.jobstores import DjangoJobStore, register_events
from django_apscheduler.models import DjangoJobExecution

logger = logging.getLogger(__name__)


def job_check_mercari_stock():
    try:
        call_command("check_mercari_stock")
    except Exception:  # noqa: BLE001
        logger.exception("check_mercari_stock job failed")


def job_fetch_ebay_listings():
    try:
        call_command("fetch_ebay_listings")
    except Exception:  # noqa: BLE001
        logger.exception("fetch_ebay_listings job failed")


class Command(BaseCommand):
    help = "メルカリ在庫確認とeBay出品取得を定期実行するスケジューラを起動する"

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=str(settings.TIME_ZONE))
        scheduler.add_jobstore(DjangoJobStore(), "default")

        interval = settings.MERCARI_CHECK_INTERVAL_MINUTES
        scheduler.add_job(
            job_check_mercari_stock,
            trigger="interval",
            minutes=interval,
            id="check_mercari_stock",
            max_instances=1,
            replace_existing=True,
        )
        scheduler.add_job(
            job_fetch_ebay_listings,
            trigger="interval",
            minutes=max(interval * 2, 60),
            id="fetch_ebay_listings",
            max_instances=1,
            replace_existing=True,
        )
        register_events(scheduler)

        self.stdout.write(
            self.style.SUCCESS(
                f"スケジューラ起動: メルカリ在庫確認は{interval}分毎に実行します。 "
                "Ctrl+C で停止します。"
            )
        )
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            self.stdout.write("スケジューラを停止しました。")
