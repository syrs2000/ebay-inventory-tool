"""
eBay Trading API (XML) クライアント。

出品一覧の取得(GetMyeBaySelling)、在庫/価格更新(ReviseInventoryStatus)、
出品終了(EndFixedPriceItem)、新規/改訂出品(AddFixedPriceItem / ReviseFixedPriceItem)
を提供する。

必要な認証情報は環境変数 (.env) から読み込む:
  EBAY_APP_ID, EBAY_DEV_ID, EBAY_CERT_ID, EBAY_AUTH_TOKEN, EBAY_SITE_ID, EBAY_ENV

Trading APIのドキュメント:
  https://developer.ebay.com/devzone/xml/docs/Reference/eBay/index.html
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

EBAY_NS = "{urn:ebay:apis:eBLBaseComponents}"


class EbayApiError(Exception):
    """eBay Trading API がエラーを返した場合に送出する例外。"""

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []


@dataclass
class EbayListingData:
    item_id: str
    title: str = ""
    sku: str = ""
    currency: str = "USD"
    price: Decimal = Decimal("0")
    quantity: int = 1
    quantity_available: int = 0
    watch_count: int = 0
    listing_url: str = ""
    custom_label: str = ""
    listing_status: str = ""  # Active / Ended 等 eBay側の生値
    # --- GetItem (ItemIDからの詳細取得) で使う追加項目 ---
    description_html: str = ""
    category_id: str = ""
    category_name: str = ""
    condition_id: str = ""
    condition_description: str = ""
    brand: str = ""
    upc: str = ""
    mpn: str = ""
    item_specifics: list = field(default_factory=list)
    image_urls: list = field(default_factory=list)


def _strip_ns(tag: str) -> str:
    return tag.replace(EBAY_NS, "")


def _find(elem, path):
    """名前空間付きXMLを簡単に辿るヘルパー。"""
    parts = path.split("/")
    cur = elem
    for p in parts:
        if cur is None:
            return None
        cur = cur.find(f"{EBAY_NS}{p}")
    return cur


def _text(elem, path, default=""):
    node = _find(elem, path)
    return node.text if node is not None and node.text is not None else default


def _decimal(value, default="0"):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return Decimal(default)


class EbayTradingClient:
    def __init__(self):
        # 設定画面(core.AppSetting)で値が入力されていればそちらを優先し、
        # 空欄なら.env側の値にフォールバックする。
        from core.models import AppSetting  # 遅延import (循環回避)

        setting = AppSetting.load()

        self.app_id = setting.ebay_app_id or settings.EBAY_APP_ID
        self.dev_id = setting.ebay_dev_id or settings.EBAY_DEV_ID
        self.cert_id = setting.ebay_cert_id or settings.EBAY_CERT_ID
        self.auth_token = setting.ebay_auth_token or settings.EBAY_AUTH_TOKEN
        self.site_id = settings.EBAY_SITE_ID
        self.api_version = settings.EBAY_TRADING_API_VERSION

        env = (setting.ebay_env or settings.EBAY_ENV).strip().lower()
        self.endpoint = (
            "https://api.sandbox.ebay.com/ws/api.dll"
            if env == "sandbox"
            else "https://api.ebay.com/ws/api.dll"
        )

    # ------------------------------------------------------------------
    # 低レベル呼び出し
    # ------------------------------------------------------------------
    def _headers(self, call_name: str) -> dict:
        return {
            "X-EBAY-API-COMPATIBILITY-LEVEL": self.api_version,
            "X-EBAY-API-DEV-NAME": self.dev_id,
            "X-EBAY-API-APP-NAME": self.app_id,
            "X-EBAY-API-CERT-NAME": self.cert_id,
            "X-EBAY-API-CALL-NAME": call_name,
            "X-EBAY-API-SITEID": self.site_id,
            "Content-Type": "text/xml",
        }

    def _post(self, call_name: str, body: str, timeout: int = 30) -> ET.Element:
        if not self.auth_token:
            raise EbayApiError(
                "EBAY_AUTH_TOKEN が設定されていません。.env を確認してください。"
            )
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<{call_name}Request xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{self.auth_token}</eBayAuthToken>
  </RequesterCredentials>
  {body}
</{call_name}Request>"""

        resp = requests.post(
            self.endpoint,
            data=envelope.encode("utf-8"),
            headers=self._headers(call_name),
            timeout=timeout,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        ack = _text(root, "Ack")
        if ack not in ("Success", "Warning"):
            errors = []
            for err in root.findall(f"{EBAY_NS}Errors"):
                errors.append(
                    {
                        "code": _text(err, "ErrorCode"),
                        "severity": _text(err, "SeverityCode"),
                        "message": _text(err, "LongMessage") or _text(err, "ShortMessage"),
                    }
                )
            raise EbayApiError(f"{call_name} failed: Ack={ack}", errors=errors)
        return root

    # ------------------------------------------------------------------
    # 出品一覧取得
    # ------------------------------------------------------------------
    def get_my_ebay_selling(self, page_number: int = 1, entries_per_page: int = 200):
        """アクティブ出品一覧を取得する (GetMyeBaySelling)。"""
        body = f"""
  <ActiveList>
    <Include>true</Include>
    <Pagination>
      <EntriesPerPage>{entries_per_page}</EntriesPerPage>
      <PageNumber>{page_number}</PageNumber>
    </Pagination>
  </ActiveList>
  <DetailLevel>ReturnAll</DetailLevel>
"""
        root = self._post("GetMyeBaySelling", body)
        active_list = _find(root, "ActiveList/ItemArray")
        results = []
        if active_list is None:
            return results, 1, 0

        for item in active_list.findall(f"{EBAY_NS}Item"):
            item_id = _text(item, "ItemID")
            title = _text(item, "Title")
            sku = _text(item, "SKU")
            currency = _text(item, "SellingStatus/CurrentPrice", "USD") and _find(
                item, "SellingStatus/CurrentPrice"
            )
            currency_code = (
                currency.attrib.get("currencyID", "USD") if currency is not None else "USD"
            )
            price = _decimal(_text(item, "SellingStatus/CurrentPrice"))
            qty = int(_text(item, "Quantity", "1") or 1)
            qty_sold = int(_text(item, "SellingStatus/QuantitySold", "0") or 0)
            watch = int(_text(item, "WatchCount", "0") or 0)
            listing_url = _text(item, "ListingDetails/ViewItemURL")
            custom_label = _text(item, "SKU")

            results.append(
                EbayListingData(
                    item_id=item_id,
                    title=title,
                    sku=sku,
                    currency=currency_code,
                    price=price,
                    quantity=qty,
                    quantity_available=max(qty - qty_sold, 0),
                    watch_count=watch,
                    listing_url=listing_url,
                    custom_label=custom_label,
                    listing_status="Active",
                )
            )

        page_info = _find(root, "ActiveList/PaginationResult")
        total_pages = int(_text(page_info, "TotalNumberOfPages", "1") or 1)
        total_entries = int(_text(page_info, "TotalNumberOfEntries", "0") or 0)
        return results, total_pages, total_entries

    def get_item(self, item_id: str) -> EbayListingData:
        """ItemIDを指定して単一出品の詳細情報を取得する (GetItem)。

        出品タグの「ItemIDから取得」ボタン用。タイトル/価格に加えて、
        説明文・カテゴリ・商品状態・Brand/UPC/MPN・Item Specifics・画像URLも取得する。
        """
        body = f"""
  <ItemID>{item_id}</ItemID>
  <DetailLevel>ReturnAll</DetailLevel>
  <IncludeItemSpecifics>true</IncludeItemSpecifics>
"""
        root = self._post("GetItem", body)
        item = _find(root, "Item")
        if item is None:
            raise EbayApiError(f"ItemID {item_id} が見つかりませんでした。")

        price = _decimal(_text(item, "StartPrice"))
        currency_node = _find(item, "StartPrice")
        currency_code = currency_node.attrib.get("currencyID", "USD") if currency_node is not None else "USD"

        item_specifics = []
        specifics_node = _find(item, "ItemSpecifics")
        if specifics_node is not None:
            for nvl in specifics_node.findall(f"{EBAY_NS}NameValueList"):
                name = _text(nvl, "Name")
                if not name:
                    continue
                values = [v.text for v in nvl.findall(f"{EBAY_NS}Value") if v.text]
                item_specifics.append({"name": name, "value": ", ".join(values)})

        def _specific(name: str) -> str:
            for s in item_specifics:
                if s["name"].strip().lower() == name.lower():
                    return s["value"]
            return ""

        image_urls = []
        pictures_node = _find(item, "PictureDetails")
        if pictures_node is not None:
            image_urls = [p.text for p in pictures_node.findall(f"{EBAY_NS}PictureURL") if p.text]

        qty_total = int(_text(item, "Quantity", "1") or 1)
        qty_sold = int(_text(item, "SellingStatus/QuantitySold", "0") or 0)

        return EbayListingData(
            item_id=_text(item, "ItemID"),
            title=_text(item, "Title"),
            sku=_text(item, "SKU"),
            currency=currency_code,
            price=price,
            quantity=qty_total,
            quantity_available=max(qty_total - qty_sold, 0),
            watch_count=int(_text(item, "WatchCount", "0") or 0),
            listing_url=_text(item, "ListingDetails/ViewItemURL"),
            custom_label=_text(item, "SKU"),
            listing_status=_text(item, "SellingStatus/ListingStatus"),
            description_html=_text(item, "Description"),
            category_id=_text(item, "PrimaryCategory/CategoryID"),
            category_name=_text(item, "PrimaryCategory/CategoryName"),
            condition_id=_text(item, "ConditionID"),
            condition_description=_text(item, "ConditionDescription") or _text(item, "ConditionDisplayName"),
            brand=_specific("Brand"),
            upc=_specific("UPC"),
            mpn=_specific("MPN"),
            item_specifics=item_specifics,
            image_urls=image_urls,
        )

    # ------------------------------------------------------------------
    # ビジネスポリシー (Payment / Shipping / Return)
    # ------------------------------------------------------------------
    def get_seller_profiles(self) -> dict:
        """アカウントに登録済みのBusiness Policies一覧を取得する (GetUserPreferences)。

        戻り値: {"payment": [{"id":..,"name":..}], "shipping": [...], "return": [...]}
        """
        body = "<ShowSellerProfilePreferences>true</ShowSellerProfilePreferences>"
        root = self._post("GetUserPreferences", body)
        result: dict = {"payment": [], "shipping": [], "return": []}

        prefs = _find(root, "SellerProfilePreferences/SupportedSellerProfiles")
        if prefs is None:
            return result

        type_map = {
            "PAYMENT": "payment",
            "SHIPPING": "shipping",
            "RETURN_POLICY": "return",
        }
        for profile in prefs.findall(f"{EBAY_NS}SupportedSellerProfile"):
            profile_id = _text(profile, "ProfileID")
            profile_name = _text(profile, "ProfileName")
            profile_type = _text(profile, "ProfileType")
            key = type_map.get(profile_type)
            if key and profile_id:
                result[key].append({"id": profile_id, "name": profile_name or profile_id})
        return result

    # ------------------------------------------------------------------
    # 在庫・価格更新 / 出品終了 (自動取り下げで使用)
    # ------------------------------------------------------------------
    def revise_inventory_status(self, item_id: str, quantity: int | None = None, price=None) -> bool:
        fields = f"<ItemID>{item_id}</ItemID>"
        if quantity is not None:
            fields += f"<Quantity>{quantity}</Quantity>"
        if price is not None:
            fields += f"<StartPrice>{price}</StartPrice>"
        body = f"""
  <InventoryStatus>
    {fields}
  </InventoryStatus>
"""
        self._post("ReviseInventoryStatus", body)
        return True

    def end_item(self, item_id: str, reason: str = "NotAvailable") -> bool:
        """出品を強制終了する。メルカリ側の売り切れ検知時の自動取り下げに使用。

        reason は eBay の EndReasonCodeType のいずれか
        (例: NotAvailable, LostOrBroken, Incorrect など)。
        """
        body = f"""
  <ItemID>{item_id}</ItemID>
  <EndingReason>{reason}</EndingReason>
"""
        self._post("EndFixedPriceItem", body)
        return True

    # ------------------------------------------------------------------
    # 出品作成・改訂 (画面3の「出品」ボタン用、MVPでは主要項目のみ)
    # ------------------------------------------------------------------
    def _item_xml(self, listing) -> str:
        specifics_xml = ""
        if listing.item_specifics:
            rows = "".join(
                f"<NameValueList><Name>{s.get('name','')}</Name>"
                f"<Value>{s.get('value','')}</Value></NameValueList>"
                for s in listing.item_specifics
                if s.get("name")
            )
            specifics_xml = f"<ItemSpecifics>{rows}</ItemSpecifics>"

        pictures_xml = ""
        if listing.image_urls:
            urls = "".join(f"<PictureURL>{u}</PictureURL>" for u in listing.image_urls if u)
            pictures_xml = f"<PictureDetails>{urls}</PictureDetails>"

        profile_parts = []
        if listing.payment_profile_id:
            profile_parts.append(
                f"<SellerPaymentProfile><PaymentProfileID>{listing.payment_profile_id}"
                f"</PaymentProfileID></SellerPaymentProfile>"
            )
        if listing.shipping_profile_id:
            profile_parts.append(
                f"<SellerShippingProfile><ShippingProfileID>{listing.shipping_profile_id}"
                f"</ShippingProfileID></SellerShippingProfile>"
            )
        if listing.return_profile_id:
            profile_parts.append(
                f"<SellerReturnProfile><ReturnProfileID>{listing.return_profile_id}"
                f"</ReturnProfileID></SellerReturnProfile>"
            )
        seller_profiles_xml = (
            f"<SellerProfiles>{''.join(profile_parts)}</SellerProfiles>" if profile_parts else ""
        )

        return f"""
  <Item>
    {f"<ItemID>{listing.item_id}</ItemID>" if listing.item_id else ""}
    <Title>{listing.title_en or listing.title_ja}</Title>
    <Description><![CDATA[{listing.description_html or listing.description_ja}]]></Description>
    <PrimaryCategory><CategoryID>{listing.category_id}</CategoryID></PrimaryCategory>
    <StartPrice currencyID="{listing.currency}">{listing.price}</StartPrice>
    <ConditionID>{listing.condition_id or 1000}</ConditionID>
    <Country>US</Country>
    <Currency>{listing.currency}</Currency>
    <SKU>{listing.custom_label or listing.sku}</SKU>
    <Quantity>{listing.quantity}</Quantity>
    <ListingDuration>GTC</ListingDuration>
    <ListingType>FixedPriceItem</ListingType>
    {pictures_xml}
    {specifics_xml}
    {seller_profiles_xml}
  </Item>
"""

    def add_fixed_price_item(self, listing) -> str:
        body = self._item_xml(listing)
        root = self._post("AddFixedPriceItem", body)
        return _text(root, "ItemID")

    def revise_fixed_price_item(self, listing) -> str:
        body = self._item_xml(listing)
        root = self._post("ReviseFixedPriceItem", body)
        return _text(root, "ItemID")
