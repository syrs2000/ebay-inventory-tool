"""
メルカリ商品ページをブラウザ自動操作(Playwright)で開き、売り切れ状態を判定する。

注意:
  メルカリは在庫確認用の公式APIを一般提供していません。本モジュールは
  商品ページのHTMLをブラウザで描画して文言を判定する方式のため、
  - サイト構造の変更で判定が壊れる可能性がある
  - 利用規約上のリスク(自動アクセス)がある
  ことを理解した上で、チェック間隔を空けて(既定30分)常識的な範囲で使用すること。
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

SOLD_OUT_KEYWORDS = [
    "売り切れました",
    "sold out",
    "Sold Out",
    "SOLD OUT",
    "この商品は販売が終了しています",
]

IN_STOCK_KEYWORDS = [
    "購入手続きへ",
    "SOLD",  # 誤検知防止のため下のロジックではsold_out優先
]


class MercariCheckError(Exception):
    pass


def check_stock_status(url: str, headless: bool | None = None, timeout_ms: int = 20000) -> str:
    """メルカリ商品ページを開き、"在庫あり" / "売り切れ" / "不明" を返す。"""
    from mercari_link.models import MercariLink  # 遅延import (循環回避)

    headless = settings.PLAYWRIGHT_HEADLESS if headless is None else headless

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise MercariCheckError(
            "playwright がインストールされていません。"
            "`pip install playwright` と `playwright install chromium` を実行してください。"
        ) from exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"
                    )
                )
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)  # SPA描画待ち
                body_text = page.inner_text("body")
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Mercari check failed for %s", url)
        raise MercariCheckError(str(exc)) from exc

    for kw in SOLD_OUT_KEYWORDS:
        if kw in body_text:
            return MercariLink.STOCK_SOLD_OUT

    # 売り切れ文言が無く、購入ボタン文言があれば在庫ありと判定
    if "購入手続きへ" in body_text or "コメントする" in body_text:
        return MercariLink.STOCK_IN_STOCK

    return MercariLink.STOCK_UNKNOWN
