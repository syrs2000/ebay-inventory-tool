# eBay 出品・在庫管理ツール (MVP)

Python / Django 製の eBay 出品・在庫管理ツールです。eBay Trading API と連携して出品の取得・編集・出品/改訂ができ、
メルカリの商品ページをブラウザ自動操作で監視して、売り切れを検知したら該当のeBay出品を自動で取り下げます。

作成時に合意したスコープ:
- MVP優先(全機能の完全再現ではなく、主要機能から着手)
- メルカリはブラウザ自動操作(Playwright)で在庫状況を確認
- ローカルPCで常時起動して使う想定
- eBay Developer 認証情報は取得済みの前提

## できること (MVP範囲)

- eBay の `GetMyeBaySelling` で出品一覧を取得し、DBに保存 (「START」ボタン相当)
- 一覧画面: 全データ / 在庫なし / 確認不可 のフィルタ、ItemID・SKU検索、CSV出力・CSV取込
- 出品編集画面: タイトル(日本語/英語)、画像URL、カテゴリ、商品状態、Brand/UPC/MPN、
  Item Specifics、価格・Best Offer・数量、利益計算(仕入価格・為替・手数料・送料等)、
  カスタムラベル/SKU、追加SKU、ディスクリプション(簡易日→英翻訳)
- 「保存して出品/更新」で eBay の `AddFixedPriceItem` / `ReviseFixedPriceItem` を呼び出し
- メルカリ商品URLを出品に紐づけ、定期的に売り切れを検知したら eBay の `EndFixedPriceItem` で自動取り下げ
- 在庫確認ログ(監査証跡)の記録
- スケジューラ (`run_scheduler` コマンド) でメルカリ在庫確認・eBay再取得を定期実行

## 含まれていないもの (今後の拡張候補)

- 画像加工/ウォーターマット合成、Store Category選択、AI提案、Amazon一覧からの自動仕入れ
- eBay カテゴリ検索UI、Item Specifics のeBay側マスタからの候補取得
- 複数ユーザー/権限管理、詳細な為替自動取得
- メルカリ以外の仕入れ元(Yahooフリマ等)との連携

## セットアップ

### 1. 前提

- Python 3.10+ (Windows PCにインストール済みであること)
- eBay Developer Program 登録済み (App ID / Dev ID / Cert ID / User Token)
  - https://developer.ebay.com/my/keys で確認できます
  - Trading API を使うため、Auth'n'Auth のユーザートークン(EBAY_AUTH_TOKEN)が必要です

### 2. インストール

```
cd ebay_tool
python -m venv venv
venv\Scripts\activate          (Windowsの場合)
pip install -r requirements.txt
playwright install chromium    (メルカリ監視に必要な初回のみ)
```

### 3. 環境変数の設定

`.env.example` を `.env` にコピーし、eBay の認証情報を入力してください。

```
copy .env.example .env
```

`.env` の主な項目:

| 変数 | 説明 |
|---|---|
| EBAY_ENV | `sandbox` または `production` |
| EBAY_APP_ID / EBAY_DEV_ID / EBAY_CERT_ID | eBay Developer Keys |
| EBAY_AUTH_TOKEN | Trading API 用のユーザートークン |
| EBAY_SITE_ID | サイトID (0=US) |
| MERCARI_CHECK_INTERVAL_MINUTES | メルカリ在庫確認の間隔(分) 既定30分 |
| PLAYWRIGHT_HEADLESS | メルカリ確認時にブラウザを表示しないか(1=非表示) |

本番のeBay認証情報が用意でき次第 `.env` に設定すれば、すぐに本番APIと通信します。
それまではUI/DB/ロジックの動作確認のみ行えます(eBay呼び出し部分はエラーメッセージを表示して安全に失敗します)。

### 4. データベース初期化

```
python manage.py migrate
python manage.py createsuperuser
```

### 5. 起動 (常時起動運用)

ローカルPCで常時起動する場合、2つのプロセスを起動しておきます。

**Webアプリ (画面操作用)**
```
python manage.py runserver
```
ブラウザで http://127.0.0.1:8000/ を開いてください。管理画面は http://127.0.0.1:8000/admin/ です。

**バックグラウンドスケジューラ (自動取り下げ用)**
```
python manage.py run_scheduler
```
これを起動しておくと、`.env` の `MERCARI_CHECK_INTERVAL_MINUTES` 間隔でメルカリ在庫を確認し、
売り切れを検知した出品は自動的にeBayから取り下げられます。Windowsのタスクスケジューラに
ログイン時起動として登録しておくと、PCを開いたときに自動で動き出します。

## 使い方の流れ

1. 出品一覧画面で「START」を押して eBay から出品を取り込む
2. 一覧から出品行をクリックして編集画面を開く
3. タイトル・画像・カテゴリ・Item Specifics・価格などを入力し、「メルカリ紐づけ」欄に
   仕入れ元のメルカリ商品URLを登録(自動取り下げを有効にする場合はチェックを入れる)
4. 「保存して出品/更新」で eBay に反映
5. `run_scheduler` を起動しておけば、以降は自動でメルカリの売り切れを検知して出品を取り下げます
6. 「メルカリ紐づけ」画面でいつでも手動確認・監視状況・ログを確認できます

## 重要な注意事項 (リスクについて)

- メルカリは在庫確認用の公式APIを一般提供していないため、本ツールは商品ページを
  ブラウザで開いて文言判定する方式を採っています。サイト構造の変更で判定精度が
  落ちる可能性があるほか、頻繁な自動アクセスは利用規約上のリスクがあるため、
  確認間隔を極端に短くしないことを推奨します(既定30分)。
- eBay Trading API のレート制限にご注意ください。大量出品がある場合は
  `fetch_ebay_listings --pages` やページングの調整が必要です。
- 誤って意図しない出品を取り下げないよう、まずは `check_mercari_stock --dry-run`
  で判定結果だけを確認してから自動取り下げを有効にすることを推奨します。

## プロジェクト構成

```
ebay_tool/
  config/            Django設定・URLルーティング
  listings/          eBay出品モデル・画面・eBay Trading APIクライアント
  mercari_link/       メルカリ紐づけモデル・在庫監視(Playwright)・自動取り下げ
  core/              スケジューラ(run_scheduler)などプロジェクト共通処理
  templates/         画面テンプレート(一覧・編集・メルカリ紐づけ)
  static/            CSS
```
