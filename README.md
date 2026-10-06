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
- 公開取得を接続した系列: Shiller CAPE (shillerdata.com の最新ie_data.xls。取得できない場合のみ更新停止中のYale版へ代替), CAPE earnings-yield minus real-yield proxy (ERP), FINRA margin debit balances, CFTC S&P 500 leveraged-fund net positions/open interest, NY Fed ACM 10-year term premium, NY Fed 12-month recession probability, NY Fed/Equifax credit-card and auto-loan flows into 30+ and 90+ day delinquency. NY Fed/Census core capital goods orders and FRB SLOOS remain connected through FRED.
- CAPE/ERP: Shiller's maintained site (shillerdata.com) is used and currently extends to 2026-09 (the Yale copy ends 2023-09 and is only a fallback). The latest months use estimated CPI/earnings per the source notes. ERP is a CAPE-based proxy.
- Recession probability: the NY Fed CSV ends at 2017-06, so the card falls back to a clearly labeled proxy computed here from FRED T10Y3M with the published probit (P = 100 × Φ(−0.5333 − 0.6330 × monthly mean 10y−3m spread), 12 months ahead). Over the overlap with the official CSV the mean absolute difference is 0.07 points. It is not an official NY Fed release.
- Cboe's downloadable total put/call CSV ends in 2019 and is stale. Cboe's newer daily statistics are only on its website/undocumented endpoints, and Cboe's terms prohibit automated access, so they are not fetched; the Put/Call card stays local-only and stale with a link to the source.
- The Cboe total put/call CSV is available and parsed in local mode only; Cboe states its use is subject to Cboe Website Terms and Conditions, so its values/history are excluded from the public JSON.
- A/D line: no free, officially licensed API/CSV exists (NYSE/Nasdaq historical breadth is sold via market-data products; Nasdaq Data Link/Stooq/StockCharts/WSJ either require paid access, block automation, or forbid redistribution; FRED has no such series). It is therefore a local-only manual-CSV series (see below), restricted in public JSON/AI prompts. The remaining items - the share of S&P constituents above their 200-day averages, and new-high/new-low breadth remain disconnected. Reconstructing these from hundreds of symbols via yfinance would create large, repeated automated downloads from an unofficial Yahoo Finance client, with rate-limit and Yahoo terms-of-use risk. No constituent history is automatically downloaded.
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

#### 毎日の入力手順 (履歴CSVなしで蓄積する方式)
Barchartの履歴CSVはプランによっては使えないため、当日の終値を手入力して `local_data/barchart_cpcs.csv` に蓄積します。
1. Barchartで `$CPCS` の終値を確認します。
2. `python add_putcall.py 0.62` を実行します (日付省略時は今日。過去日は `python add_putcall.py 0.62 2026-10-02`)。ヘッダー(`Date,Close`)は自動作成、同日は上書き、数値でない値・0以下・10超・未来日は拒否されます。
3. `python fetch_macro.py --local` を実行して `macro.local.json` を更新します。
- 蓄積が30日未満の間は、カードに「蓄積N日」と表示し、歴史的位置(パーセンタイル)は表示しません。
- ファイルは `local_data/` (gitignore済み) にのみ保存され、公開版には含まれません。

## AIアナリスト分析 (Gemini)

- `python insights.py` が各カテゴリの現在値・歴史的位置・最終観測日・stale/未接続状態を Gemini に渡し、短い日本語コメントを `insights.json` に出力します (カテゴリごと1コール + 全体俯瞰1コール、temperature 0.2)。投資助言・総合スコアは出力させません。
- キー: GitHub Secrets に `GEMINI_API_KEY` を登録 (ローカルは `.env`)。モデルは `GEMINI_MODEL` (既定 `gemini-3.8-flash`、失敗時 `gemini-2.5-flash`)。キー未設定/API失敗時は「未生成」表示になり、他の表示には影響しません。入力が前回と同一なら再生成しません。
- 公開版 (`insights.json`) は再配布制限指標を入力にも出力にも含めません。ローカル版 (`python insights.py --local`) は `macro.local.json` から `insights.local.json` (gitignore) を生成します。
- 注意: Gemini API の無料枠では入力が Google の製品改善に使われ得ます。制限データを含むローカル分析には課金済みキーを推奨します。


### 騰落(A/D)ラインの手動CSV入力 (ローカル専用)
公式の無料・再配布可能な自動取得経路がないため、日次の advancing/declining issues を手動で記録します。CSV は `local_data/ad_issues.csv` (gitignore済み) に保存され、`AD_ISSUES_CSV` 環境変数で保存先を変更できます。再配布制限データとして扱い、公開版 (`macro.json`/`insights.json`) に値や履歴は含まれません。

毎日の入力手順:
1. NYSE または Nasdaq の Market Diary、もしくは契約中のデータサービスで advancing / declining / unchanged issues を確認します。個人閲覧の範囲内で利用し、提供元の利用条件に従ってください。画面値の再配布、公開JSONへの追加、第三者への共有はしないでください。
2. リポジトリのフォルダーで次を実行します。`--date` を省略するとPCの当日の日付になります。
   ```powershell
   python add_ad.py --market NYSE --adv 1500 --dec 1700 --unch 100
   python fetch_macro.py --local
   ```
   日付を指定する場合は `--date 2026-10-05` のようにします。同じ日付・市場を再入力すると置き換わり、別市場の行は保持されます。`--unch` は省略可能で、その場合は 0 です。
3. ローカル版を開き、A/Dカードを確認します。最新日の上昇比率 `advances / (advances + declines)` と直近10観測日の平均、単日の advance − decline 棒グラフを表示します。目安は50%前後が拮抗、70%以上が強い、30%以下が弱い状態です。CSVを更新するまで値は変わりません。最終観測が7日超前の場合は `stale` と表示します。

CSVヘッダーは自動作成されます。形式は `date,market,advances,declines,unchanged` です。`--unch` は任意で、省略時は0として扱い、A/Dラインと上昇比率には使いません。A/Dラインは日次の advances − declines を時系列累積します。`AD_MARKET` で対象市場を指定できます。初期は少数の観測日となるためカードに「蓄積N日」と表示し、歴史的位置は参考程度とします。CSVに入力した元系列の累積起点は最初の観測日です。A/Dラインの絶対値には意味がなく、傾きと指数との乖離を見るための指標です。

同期間の比較指数として、NYSE は NYSE Composite (`^NYA`)、Nasdaq は Nasdaq Composite (`^IXIC`) の日次履歴をローカル実行時に Yahoo Finance 経由で取得します。チャートでは基準日のA/D累積値を0とした変化量と、指数の基準日比騰落率を重ねます。直近10観測日の指数高値/安値更新とA/Dの方向が食い違う場合は、相場の裾野の変化を「示唆」として短く注記します。2系列はそれぞれ独立した縦軸で描画するため、線の高さや振幅を直接比較しないでください。指数データは第三者の再配布制限データとしてローカルにのみ含め、公開JSON・公開AI分析には出しません。履歴の入手可否やYahoo Financeの利用条件により指数比較が取得できないことがあり、その場合は取得できない旨を表示します。S&P 500構成銘柄限定のA/Dは対象外です。
