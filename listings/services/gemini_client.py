"""
Gemini API を使った簡易翻訳クライアント。

Google Generative Language API (REST) を requests で直接呼び出す
(公式SDK非依存、requirements.txtの追加なしで動く)。
APIキーは設定画面(core.AppSetting.gemini_api_key)で管理する。
未設定・呼び出し失敗時は呼び出し元(listings.views.translate_text)側で
deep_translator (Google翻訳) にフォールバックする想定。
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)


class GeminiApiError(Exception):
    pass


def _get_api_key() -> str:
    from core.models import AppSetting  # 遅延import (循環回避)

    return (AppSetting.load().gemini_api_key or "").strip()


def is_configured() -> bool:
    return bool(_get_api_key())


def translate_ja_to_en(text: str, timeout: int = 30) -> str:
    """日本語テキストをGemini APIで自然な英語(eBay出品向け)に翻訳する。"""
    api_key = _get_api_key()
    if not api_key:
        raise GeminiApiError("Gemini APIキーが設定されていません。設定画面から登録してください。")
    if not text.strip():
        return ""

    prompt = (
        "You are a professional e-commerce listing translator. "
        "Translate the following Japanese product description into natural, "
        "concise English suitable for an eBay listing. "
        "Output ONLY the translated English text, with no preamble, "
        "no quotation marks, and no explanation.\n\n"
        f"{text}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }

    try:
        resp = requests.post(
            GEMINI_API_URL,
            params={"key": api_key},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("Gemini translation request failed: %s", exc)
        raise GeminiApiError(f"Gemini API呼び出しに失敗しました: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — 想定外のエラーもGeminiApiErrorに正規化してフォールバックを確実にする
        logger.warning("Gemini translation unexpected error: %s", exc)
        raise GeminiApiError(f"Gemini呼び出し中に予期しないエラーが発生しました: {exc}") from exc

    candidates = data.get("candidates") or []
    if not candidates:
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        raise GeminiApiError(
            f"Geminiから翻訳結果を取得できませんでした ({block_reason or '不明なエラー'})。"
        )
    parts = candidates[0].get("content", {}).get("parts", [])
    translated = "".join(p.get("text", "") for p in parts).strip()
    if not translated:
        raise GeminiApiError("Geminiの応答が空でした。")
    return translated
