"""
為替レート取得クライアント。

無料・APIキー不要の frankfurter.app (欧州中央銀行レート基準) からUSD→JPYの
最新レートを取得する。「為替」欄の自動入力ボタン用。
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import requests

logger = logging.getLogger(__name__)

FX_API_URL = "https://api.frankfurter.app/latest"


class FxRateError(Exception):
    pass


def get_usd_jpy_rate(timeout: int = 10) -> Decimal:
    """USD -> JPY の最新為替レートを取得する。取得に失敗した場合はFxRateErrorを送出する。"""
    try:
        resp = requests.get(FX_API_URL, params={"from": "USD", "to": "JPY"}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"]["JPY"]
        return Decimal(str(rate))
    except (requests.RequestException, KeyError, TypeError, InvalidOperation, ValueError) as exc:
        logger.warning("FX rate fetch failed: %s", exc)
        raise FxRateError(f"為替レート取得に失敗しました: {exc}") from exc
