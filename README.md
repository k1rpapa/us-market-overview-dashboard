# 米国市場 俯瞰ダッシュボード

米国株式市場の大局を、指標ごとに長期推移と歴史的レンジで見る個人用ダッシュボード。静的サイト(GitHub Pages)で、データは `fetch_macro.py` が生成する `macro.json`。

- 総合スコアは出しません。取得できた値だけを表示し、未接続・取得失敗は理由を明示します。
- 一部指標は代理/近似です(カード上に明記)。公的な安定取得手段のない指標は「未接続」。
- APIキー(`FRED_API_KEY`, `EIA_API_KEY`)はGitHub Secretsからのみ読み込み、コミット・出力しません。

## 開発
```
pip install -r requirements.txt
python fetch_macro.py          # macro.json を生成
python fetch_macro.py --local  # macro.local.json を生成(ローカル限定データ含む)
python -m unittest discover -s tests
node --test tests/macro.test.js
python -m http.server 8000 --bind 0.0.0.0 # http://localhost:8000
```

### ローカル版 (再配布制限データを含む)
1. `.env.example` を `.env` にコピーし、必要なら手元で取得した `FRED_API_KEY` と `EIA_API_KEY` を設定します。`.env` はGit管理対象外です。キーがなくても公開CSVで取得を試みますが、FRED公式APIやEIA系列はキー設定を推奨します。
2. 仮想環境を作成して依存を入れます: `python -m venv .venv`、`.venv\Scripts\Activate.ps1`、`pip install -r requirements.txt`。
3. `python fetch_macro.py --local` を実行すると、同じフォルダーに `macro.local.json` を生成します。通常の `python fetch_macro.py` は制限データを除いた公開用 `macro.json` を出力します。
4. `python -m http.server 8000 --bind 0.0.0.0` を起動し、このPCの `http://localhost:8000` を開きます。ローカルJSONが存在すると優先表示し、無ければ `macro.json` にフォールバックします。
5. スマートフォンからはPCと同じWi-Fiに接続し、PCのLAN IPv4アドレス（Windowsで `ipconfig` を実行して確認）を使って `http://<PCのIPv4アドレス>:8000` を開きます。Windows Defender FirewallでPythonのプライベートネットワーク受信を許可してください。モバイル表示中もローカルJSONの存在時はローカル版が優先されます。

`macro.local.json` には第三者の再配布制限がある系列を含み得ます。ローカル端末内だけで扱い、GitHubやその他の場所へアップロード、コミット、共有しないでください。`.gitignore` とPagesの明示的な公開ファイル許可リストで除外しています。

### Windows タスクスケジューラで日次更新
1. 上記の仮想環境と `.env` を準備し、一度 `python fetch_macro.py --local` が成功することを確認します。
2. タスクスケジューラで「基本タスクの作成」→名前 (例: `US Market Dashboard Refresh`) →「毎日」→実行時刻を設定します。
3. 「プログラムの開始」を選び、プログラムに `powershell.exe`、引数に `-NoProfile -ExecutionPolicy Bypass -File "C:\path\to\us-market-overview-dashboard\refresh-local.ps1"`、開始にリポジトリのフォルダーを指定します。スクリプトは `.venv` があればそのPythonを使い、`macro.local.json` を更新します。
4. 必要に応じて「ユーザーがログオンしているかどうかにかかわらず実行する」を設定します。ローカルサーバーをスマホから利用する場合、タスクではなくPC上で `python -m http.server 8000 --bind 0.0.0.0` も起動しておきます。

## 公開手順
1. Settings → Secrets and variables → Actions に `FRED_API_KEY`, `EIA_API_KEY` を登録
2. Settings → Pages → Source を「GitHub Actions」に設定
3. Actions → 「Update data and deploy Pages」を手動実行

## データの扱い
- FRED経由の系列は出典(FRED/元機関)を各カードに表示。ICE BofA社債OASなど第三者の再配布制限があるデータと、Yahoo Finance由来の指数・ETF系列(S&P500、SPY/RSP、VIX)は、公開JSONに値・履歴を含めず「再配布制限」と表示します。
- 公開取得を接続した系列: Shiller CAPE (shillerdata.com ???ie_data.xls?????????????????Yale????), CAPE earnings-yield minus real-yield proxy (ERP), FINRA margin debit balances, CFTC S&P 500 leveraged-fund net positions/open interest, NY Fed ACM 10-year term premium, NY Fed 12-month recession probability, NY Fed/Equifax credit-card and auto-loan flows into 30+ and 90+ day delinquency. NY Fed/Census core capital goods orders and FRB SLOOS remain connected through FRED.
- CAPE/ERP: Shiller's maintained site (shillerdata.com) is used and currently extends to 2026-09 (the Yale copy ends 2023-09 and is only a fallback). The latest months use estimated CPI/earnings per the source notes. ERP is a CAPE-based proxy.
- Recession probability: the NY Fed CSV ends at 2017-06, so the card falls back to a clearly labeled proxy computed here from FRED T10Y3M with the published probit (P = 100 ? ?(?0.5333 ? 0.6330 ? monthly mean 10y?3m spread), 12 months ahead). Over the overlap with the official CSV the mean absolute difference is 0.07 points. It is not an official NY Fed release.
- Cboe's downloadable total put/call CSV ends in 2019 and is stale. Cboe's newer daily statistics are only on its website/undocumented endpoints, and Cboe's terms prohibit automated access, so they are not fetched; the Put/Call card stays local-only and stale with a link to the source.
- The Cboe total put/call CSV is available and parsed in local mode only; Cboe states its use is subject to Cboe Website Terms and Conditions, so its values/history are excluded from the public JSON.
- A/D line, the share of S&P constituents above their 200-day averages, and new-high/new-low breadth remain disconnected. Reconstructing these from hundreds of symbols via yfinance would create large, repeated automated downloads from an unofficial Yahoo Finance client, with rate-limit and Yahoo terms-of-use risk. No constituent history is automatically downloaded.
- Earnings revisions remain unconnected because they are commercial. CNN Fear & Greed remains link-only.
- This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.

### Barchart $CPCS (Put/Call) 手動CSV取込 (ローカル専用)
Cboeの公開CSVが2019年で止まっているため、Barchart会員が手動でダウンロードしたCSVをローカル版のPut/Callに使えます。公開版 (`macro.json`) には含まれません。
1. Barchartにログインし、`$CPCS` (Equity Put/Call Ratio) の Historical Download で日次CSVをダウンロードします (会員プランごとの取得期間・回数制限に従ってください)。
2. `local_data/barchart_cpcs.csv` として保存します (`local_data/` はgitignore済み。別の場所なら環境変数 `BARCHART_CPCS_CSV` にパスを指定)。
3. `python fetch_macro.py --local` を実行すると、`macro.local.json` のPut/Callカードがこのファイルを優先して表示します。ファイルがなければ従来のCboe CSV(古い場合はstale表示)にフォールバックします。
- 期待する形式: ヘッダー行に `Time`(または`Date`)と `Last`(または`Close`)列を含むCSV。日付は `YYYY-MM-DD` または `MM/DD/YYYY`。末尾の `Downloaded from Barchart.com...` 等の行は無視されます。
- `$CPCS` は株式(エクイティ)のみの比率で、Cboe全体比率とは水準が異なります。カードにもその旨を表示します。更新するには定期的にCSVを再ダウンロードしてください。
- Barchartのウェブサイトのスクレイピングや自動ログインは行いません。自動取得を行う場合は、契約プランにBarchart OnDemand等のAPI権限とデータ保存範囲が含まれるか確認が必要です。
