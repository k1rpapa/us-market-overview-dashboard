# 米国市場 俯瞰ダッシュボード

米国株式市場の大局を、指標ごとに長期推移と歴史的レンジで見る個人用ダッシュボード。静的サイト(GitHub Pages)で、データは `fetch_macro.py` が生成する `macro.json`。

- 総合スコアは出しません。取得できた値だけを表示し、未接続・取得失敗は理由を明示します。
- 一部指標は代理/近似です(カード上に明記)。公的な安定取得手段のない指標は「未接続」。
- APIキー(`FRED_API_KEY`, `EIA_API_KEY`)はGitHub Secretsからのみ読み込み、コミット・出力しません。

## 開発
```
pip install yfinance pandas
python fetch_macro.py          # macro.json を生成
python -m unittest discover -s tests
node --test tests/macro.test.js
python -m http.server 8000     # http://localhost:8000
```

## 公開手順
1. Settings → Secrets and variables → Actions に `FRED_API_KEY`, `EIA_API_KEY` を登録
2. Settings → Pages → Source を「GitHub Actions」に設定
3. Actions → 「Update data and deploy Pages」を手動実行

## データの扱い
- FRED経由の系列は出典(FRED/元機関)を各カードに表示。ICE BofA社債OASなど第三者の再配布制限があるデータと、Yahoo Finance由来の指数・ETF系列(S&P500、SPY/RSP、VIX)は、公開JSONに値・履歴を含めず「再配布制限」と表示します。
- This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.
