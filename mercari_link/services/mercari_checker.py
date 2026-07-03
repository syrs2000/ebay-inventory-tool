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
import re

from django.conf import settings

logger = logging.getLogger(__name__)

_MERCARI_ITEM_ID_RE = re.compile(r"(m\d{6,15})")


def extract_mercari_id(url: str) -> str:
    """メルカリ商品URL(例: https://jp.mercari.com/item/m12345678901)から
    'm+数字'形式の商品IDを抽出する。メルカリSKU/管理番号として使う。
    抽出できない場合は空文字を返す。
    """
    if not url:
        return ""
    match = re.search(r"/item/(m\d+)", url)
    if match:
        return match.group(1)
    match = _MERCARI_ITEM_ID_RE.search(url)
    return match.group(1) if match else ""

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


def extract_product_images(
    url: str, headless: bool | None = None, timeout_ms: int = 20000
) -> list[str]:
    """メルカリ商品ページをPlaywrightで開き、商品画像URLの一覧を取得する。

    出品編集画面の「メルカリから画像取得」ボタン用。メルカリのCDN
    (static.mercdn.net 等)から配信されている画像のみを対象とする。
    サイト構造の変更で取得できなくなる可能性がある点は check_stock_status と同様。
    """
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
                srcs = page.eval_on_selector_all("img", "els => els.map(e => e.src)")
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Mercari image extraction failed for %s", url)
        raise MercariCheckError(str(exc)) from exc

    seen = set()
    images = []
    for src in srcs or []:
        if not src:
            continue
        if ("static.mercdn.net" in src or "static.mercari.com" in src) and src not in seen:
            seen.add(src)
            images.append(src)

    if not images:
        raise MercariCheckError(
            "商品画像が見つかりませんでした。ページ構造が変わっている可能性があります。"
        )
    return images


def extract_product_description(
    url: str, headless: bool | None = None, timeout_ms: int = 20000
) -> str:
    """メルカリ商品ページをPlaywrightで開き、商品説明文(日本語)を取得する。

    出品編集画面の「メルカリから説明文取得」ボタン用。メルカリは説明文を
    <pre> タグで描画することが多いため、まずそれを試し、
    取得できなければ og:description メタタグにフォールバックする。
    サイト構造の変更で取得できなくなる可能性がある点は他のメルカリ取得機能と同様。
    """
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

                texts = page.eval_on_selector_all("pre", "els => els.map(e => e.innerText)")
                candidate = max(texts, key=len, default="") if texts else ""

                if not candidate.strip():
                    candidate = (
                        page.get_attribute('meta[property="og:description"]', "content") or ""
                    )
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Mercari description extraction failed for %s", url)
        raise MercariCheckError(str(exc)) from exc

    candidate = (candidate or "").strip()
    if not candidate:
        raise MercariCheckError(
            "商品説明が見つかりませんでした。ページ構造が変わっている可能性があります。"
        )
    return candidate
