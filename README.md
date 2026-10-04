# 米国市場 俯瞰ダッシュボード

米国株式市場の大局を、指標ごとに長期推移と歴史的レンジで見る個人用ダッシュボード。静的サイト(GitHub Pages)で、データは `fetch_macro.py` が生成する `macro.json`。

- 総合スコアは出しません。取得できた値だけを表示し、未接続・取得失敗は理由を明示します。
- 一部指標は代理/近似です(カード上に明記)。公的な安定取得手段のない指標は「未接続」。
- APIキー(`FRED_API_KEY`, `EIA_API_KEY`)はGitHub Secretsからのみ読み込み、コミット・出力しません。

## 開発
```
pip install yfinance pandas
python fetch_macro.py          # macro.json を生成
python fetch_macro.py --local  # macro.local.json を生成(ローカル限定データ含む)
python -m unittest discover -s tests
node --test tests/macro.test.js
python -m http.server 8000 --bind 0.0.0.0 # http://localhost:8000
```

### ローカル版 (再配布制限データを含む)
1. `.env.example` を `.env` にコピーし、必要なら手元で取得した `FRED_API_KEY` と `EIA_API_KEY` を設定します。`.env` はGit管理対象外です。キーがなくても公開CSVで取得を試みますが、FRED公式APIやEIA系列はキー設定を推奨します。
2. 仮想環境を作成して依存を入れます: `python -m venv .venv`、`.venv\Scripts\Activate.ps1`、`pip install yfinance pandas`。
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
- This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.
