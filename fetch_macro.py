"""米国市場俯瞰ダッシュボード用の指標データ(macro.json)を生成する。

- 取得できた値のみを出力する。取得不能・未接続の指標は値を持たず status と reason を明示する。
- EIA_API_KEY は環境変数からのみ読み込み、出力ファイルやログには含めない。
"""
import csv
import argparse
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

MAX_HISTORY_POINTS = 360
USER_AGENT = "Mozilla/5.0 (CapitalFlowAnalyzer macro fetch)"

GROUPS = [
    {"id": "valuation", "name": "割高感・利益"},
    {"id": "momentum", "name": "モメンタム・市場の広がり"},
    {"id": "credit", "name": "信用・センチメント"},
    {"id": "economy", "name": "景気"},
    {"id": "rates", "name": "金利"},
    {"id": "energy", "name": "エネルギー"},
]


def _spec(id, group, name, definition, reading, caution, source, source_url, frequency,
          unit="", kind="pending", params=None, reason="", formula="", restricted=False):
    return {
        "id": id, "group": group, "name": name, "definition": definition,
        "reading": reading, "caution": caution, "source": source,
        "source_url": source_url, "frequency": frequency, "unit": unit,
        "kind": kind, "params": params or {}, "reason": reason, "formula": formula,
        "restricted": restricted,
    }


FRED_URL = "https://fred.stlouisfed.org/series/"

SPECS = [
    _spec("cape", "valuation", "Shiller CAPE",
          "S&P500の株価を過去10年の平均インフレ調整後利益で割った景気循環調整PER。",
          "歴史的レンジの上位ほど長期の割高感が強い局面。",
          "短期の売買タイミング指標ではない。会計基準の変化で過去比較にズレが出る。",
          "Robert Shiller (Yale)", "http://www.econ.yale.edu/~shiller/data.htm", "月次",
          reason="公式配布はExcelで安定したAPIがないため未接続。"),
    _spec("erp", "valuation", "株式リスクプレミアム (ERP)",
          "株式の期待リターンが無リスク金利をどれだけ上回るか。",
          "低いほど株式の上乗せ報酬が薄い。",
          "利益の定義(予想/実績/CAPE)で値が大きく変わる。",
          "FRED (DFII10) + CAPE", FRED_URL + "DFII10", "日次/月次", unit="%",
          formula="ERP = 1 / CAPE − 実質10年金利(DFII10)。CAPE接続後に算出。",
          reason="CAPE未接続のため算出保留。"),
    _spec("eps_revision", "valuation", "S&P500 利益予想修正幅",
          "アナリストの1株利益予想が上方/下方どちらへ修正されているかの比率。",
          "上方修正優勢なら利益モメンタムが改善。",
          "予想は楽観に偏りやすい。",
          "LSEG I/B/E/S, FactSet (商用)", "https://insight.factset.com/topic/earnings", "週次",
          reason="商用データで公的な取得手段がないため未接続。"),
    _spec("sp500_200d", "momentum", "S&P500 200日線乖離 (モメンタム)",
          "S&P500終値の200日単純移動平均からの乖離率。",
          "プラスは長期上昇トレンド、マイナスは下降トレンド。大きなプラスは過熱の目安。",
          "トレンド追随指標で転換は遅れる。", "Yahoo Finance (^GSPC)",
          "https://finance.yahoo.com/quote/%5EGSPC", "日次", "%", kind="yf_momentum", restricted=True,
          params={"ticker": "^GSPC", "window": 200}),
    _spec("ad_line", "momentum", "騰落(A/D)ライン",
          "値上がり銘柄数−値下がり銘柄数の累積。",
          "指数が上昇してもA/Dが伴わなければ上昇の裾野が狭い。",
          "取引所ごとに定義が異なる。", "NYSE / Nasdaq (商用ベンダー)",
          "https://www.nyse.com/market-data", "日次",
          reason="公的な全銘柄騰落データの安定取得手段がないため未接続。"),
    _spec("pct_above_200d", "momentum", "200日線上銘柄比率",
          "指数構成銘柄のうち終値が200日線より上にある割合。",
          "高いほど上昇の裾野が広い。極端な低下は広範な弱さ。",
          "構成銘柄の履歴データが必要で、無料APIでは再現性が低い。",
          "S&P Dow Jones Indices (商用)", "https://www.spglobal.com/spdji/en/", "日次",
          reason="構成銘柄の全履歴が必要なため未接続。"),
    _spec("new_hi_lo", "momentum", "新高値−新安値 / McClellan",
          "52週新高値銘柄数と新安値銘柄数の差、およびA/D差の19/39日EMA差(McClellan)。",
          "新高値が減る中での指数上昇はダイバージェンス。",
          "A/Dデータ依存。", "NYSE (商用ベンダー)", "https://www.nyse.com/market-data", "日次",
          reason="A/Dと同じ理由で未接続。"),
    _spec("cap_vs_equal", "momentum", "時価総額加重 vs 均等加重 (集中度)",
          "S&P500 時価総額加重ETF(SPY)に対する均等加重ETF(RSP)の比の逆数 SPY/RSP。",
          "上昇は少数の大型株への集中が進んでいることを示す。",
          "ETFの価格比であり、構成比そのものではない。配当/経費の差も含む。",
          "Yahoo Finance (SPY, RSP)", "https://finance.yahoo.com/quote/RSP", "日次", "比",
          kind="yf_ratio", restricted=True, params={"numerator": "SPY", "denominator": "RSP"},
          formula="SPY終値 / RSP終値"),
    _spec("hy_oas", "credit", "ハイイールド社債 OAS", "米国HY債の対国債オプション調整後スプレッド。",
          "拡大は信用不安・リスクオフ、極端な縮小は信用面の油断。",
          "スプレッドの水準は格付け構成の変化にも左右される。",
          "ICE BofA via FRED", FRED_URL + "BAMLH0A0HYM2", "日次", "%",
          kind="fred", restricted=True, params={"series": "BAMLH0A0HYM2"}),
    _spec("ig_oas", "credit", "投資適格社債 OAS", "米国IG債の対国債オプション調整後スプレッド。",
          "拡大は信用環境の悪化。HYより早く動かないことも多い。",
          "金利水準の影響を受けるため単独で判断しない。",
          "ICE BofA via FRED", FRED_URL + "BAMLC0A0CM", "日次", "%",
          kind="fred", restricted=True, params={"series": "BAMLC0A0CM"}),
    _spec("nfci", "credit", "シカゴ連銀 NFCI", "金融環境の総合指数。0が平均、プラスが平均より引き締まり。",
          "上昇は資金調達環境の悪化。", "週次で改定されることがある。",
          "Chicago Fed via FRED", FRED_URL + "NFCI", "週次", "指数",
          kind="fred", params={"series": "NFCI"}),
    _spec("margin_debt", "credit", "米国マージン残高", "証券会社の信用取引の借入残高。",
          "急増はレバレッジ過熱、急減は強制決済局面の兆候。",
          "月次で公表が遅れる。名目値なので株価水準との比較が必要。",
          "FINRA", "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics",
          "月次", reason="公式はWebページ掲載のみでAPIがなく未接続。"),
    _spec("fear_greed", "credit", "CNN Fear & Greed",
          "7つの市場指標を合成したセンチメント指数。",
          "極端な恐怖/強欲は逆張りの材料にされることがある。",
          "構成要素に本ダッシュボードの指標(モメンタム・VIX・Put/Call等)と重複する。公式APIは非公開。",
          "CNN Business", "https://www.cnn.com/markets/fear-and-greed", "日次", kind="link",
          reason="公式の取得APIが確認できないため未接続。リンク先で確認。"),
    _spec("put_call", "credit", "プット/コール比率", "オプション取引のプット出来高÷コール出来高。",
          "高いほど弱気/ヘッジ需要が強い。極端値は逆張りの目安。",
          "ヘッジ目的の取引も含まれる。",
          "Cboe", "https://www.cboe.com/us/options/market_statistics/daily/", "日次",
          reason="公式CSVの安定した取得手段を確認できず未接続。"),
    _spec("vix_curve", "credit", "VIX先物カーブ (近似: VIX/VIX3M)",
          "30日物VIXと3か月物VIX3Mの比。",
          "1超(バックワーデーション)は短期の警戒が強い。1未満は通常のコンタンゴ。",
          "先物カーブそのものではなく指数ベースの近似。",
          "Yahoo Finance (^VIX, ^VIX3M)", "https://finance.yahoo.com/quote/%5EVIX", "日次", "比",
          kind="yf_ratio", restricted=True, params={"numerator": "^VIX", "denominator": "^VIX3M"},
          formula="VIX / VIX3M"),
    _spec("yield_curve", "economy", "イールドカーブ (10年−3か月)", "米国債10年と3か月の利回り差。",
          "マイナス(逆イールド)は過去に景気後退に先行しやすい。",
          "逆イールド解消後に景気後退が来る例も多く、時期は不定。",
          "Fed via FRED", FRED_URL + "T10Y3M", "日次", "%",
          kind="fred", params={"series": "T10Y3M"}),
    _spec("recession_prob", "economy", "NY連銀 後退確率", "イールドカーブから推計した12か月先の景気後退確率。",
          "高いほど逆イールド起点の後退リスクが高いとモデルが示す。",
          "単一モデルによる推計。", "NY Fed", "https://www.newyorkfed.org/research/capital_markets/ycfaq",
          "月次", reason="公式はExcel配布でFREDにも未掲載のため未接続。"),
    _spec("card_delinq", "economy", "クレジットカード延滞率 (代理指標)",
          "商業銀行のカードローン延滞率。NY連銀の「延滞移行率」の代理で、定義は異なる。",
          "上昇は家計の返済余力の低下。", "移行率ではなく延滞残高比率。自動車ローンは未接続。",
          "Fed via FRED", FRED_URL + "DRCCLACBS", "四半期", "%",
          kind="fred", params={"series": "DRCCLACBS"}),
    _spec("sloos", "economy", "SLOOS 消費者貸出基準 (カード)",
          "銀行がカードローン基準を厳格化したと答えた割合−緩和した割合(ネット%)。",
          "上昇は信用供給の絞り込み。", "四半期の調査で結果は遅れて公表される。",
          "FRB SLOOS via FRED", FRED_URL + "DRTSCLCC", "四半期", "%",
          kind="fred", params={"series": "DRTSCLCC"}),
    _spec("core_capex", "economy", "コア資本財受注", "非国防資本財(航空機除く)の新規受注。設備投資の先行指標。",
          "減速は企業の投資意欲の低下。", "名目値で月次変動が大きい。",
          "Census via FRED", FRED_URL + "NEWORDER", "月次", "百万$",
          kind="fred", params={"series": "NEWORDER"}),
    _spec("real_yield", "rates", "実質金利 (10年TIPS)", "10年物インフレ連動国債の利回り。",
          "上昇は株式の割引率上昇で割高株に逆風。", "TIPSの需給でも変動する。",
          "Fed via FRED", FRED_URL + "DFII10", "日次", "%",
          kind="fred", params={"series": "DFII10"}),
    _spec("term_premium", "rates", "NY連銀 ACMタームプレミアム",
          "長期債を保有する見返りとして要求される上乗せ利回り(10年)。",
          "上昇は長期金利の上昇が期待ではなく需給/不確実性起因であることを示す。",
          "モデル推計値で改定される。", "NY Fed",
          "https://www.newyorkfed.org/research/data_indicators/term-premia-tabs", "日次",
          reason="公式はExcel配布。FREDのKim-Wrightとは別モデルのため代用せず未接続。"),
    _spec("wti", "energy", "WTI原油", "WTI原油スポット価格。",
          "急騰はインフレ・コスト圧力、急落は需要懸念の可能性。", "地政学や在庫要因で大きく振れる。",
          "EIA via FRED", FRED_URL + "DCOILWTICO", "日次", "$/bbl",
          kind="fred", params={"series": "DCOILWTICO"}),
    _spec("diesel_price", "energy", "ディーゼル小売価格", "米国平均の小売ディーゼル(No.2)価格。",
          "物流・産業コストの先行的な圧力。", "小売価格は税・流通マージンを含む。",
          "EIA via FRED", FRED_URL + "GASDESW", "週次", "$/gal",
          kind="fred", params={"series": "GASDESW"}),
    _spec("distillate_stocks", "energy", "ディスティレート在庫", "米国の留出油(ディーゼル等)在庫。",
          "低水準はディーゼル価格の上振れ要因。", "季節性が強いため同時期比較が必要。",
          "EIA API", "https://www.eia.gov/opendata/", "週次", "千bbl", kind="eia",
          params={"route": "petroleum/stoc/wstk", "series": "WDISTUS1"},
          reason="EIA_API_KEY が未設定のため取得していない。"),
    _spec("diesel_crude_spread", "energy", "ディーゼル−原油 価格差",
          "小売ディーゼルを$/bblに換算した額とWTIの差。精製マージンの粗い目安。",
          "拡大は精製・流通マージンの上昇またはディーゼル需給の逼迫。",
          "小売価格ベースで税・流通費を含み、純粋なクラックスプレッドではない。",
          "EIA via FRED", FRED_URL + "GASDESW", "週次", "$/bbl", kind="derived",
          params={"left": "diesel_price", "right": "wti", "factor": 42},
          formula="ディーゼル小売($/gal) × 42 − WTI($/bbl)"),
]


def _http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8")


def parse_fred_csv(text):
    series = []
    reader = csv.reader(io.StringIO(text))
    next(reader, None)
    for row in reader:
        if len(row) < 2:
            continue
        try:
            series.append((row[0], float(row[1])))
        except ValueError:
            continue
    return series


def fetch_fred(series_id, http_get=_http_get):
    """FRED_API_KEY があれば公式API、なければ公開CSVから取得する。"""
    key = os.environ.get("FRED_API_KEY")
    if key:
        query = urllib.parse.urlencode({"series_id": series_id, "api_key": key, "file_type": "json"})
        payload = json.loads(http_get("https://api.stlouisfed.org/fred/series/observations?" + query))
        series = []
        for o in payload.get("observations", []):
            try:
                series.append((o["date"], float(o["value"])))
            except (KeyError, ValueError):
                continue
    else:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + urllib.parse.quote(series_id)
        series = parse_fred_csv(http_get(url))
    if not series:
        raise ValueError("empty series")
    return series

def fetch_eia(params, http_get=_http_get):
    key = os.environ.get("EIA_API_KEY")
    if not key:
        raise RuntimeError("EIA_API_KEY not set")
    query = urllib.parse.urlencode([
        ("api_key", key), ("frequency", "weekly"), ("data[0]", "value"),
        ("facets[series][]", params["series"]), ("sort[0][column]", "period"),
        ("sort[0][direction]", "asc"), ("length", "5000"),
    ])
    payload = json.loads(http_get(f"https://api.eia.gov/v2/{params['route']}/data/?{query}"))
    rows = payload.get("response", {}).get("data", [])
    series = [(r["period"], float(r["value"])) for r in rows if r.get("value") is not None]
    if not series:
        raise ValueError("empty series")
    return series


def _yf_close(ticker):
    if not YFINANCE_AVAILABLE:
        raise RuntimeError("yfinance not installed")
    df = yf.download(ticker, period="max", progress=False, auto_adjust=True)["Close"]
    if hasattr(df, "columns"):
        df = df.iloc[:, 0]
    df = df.dropna()
    if len(df) == 0:
        raise ValueError("empty series")
    return [(d.strftime("%Y-%m-%d"), float(v)) for d, v in df.items()]


def moving_average_deviation(series, window):
    out = []
    total = 0.0
    for i, (d, v) in enumerate(series):
        total += v
        if i >= window:
            total -= series[i - window][1]
        if i >= window - 1:
            out.append((d, round((v / (total / window) - 1) * 100, 3)))
    return out


def ratio_series(num, den):
    den_map = dict(den)
    return [(d, round(v / den_map[d], 5)) for d, v in num if den_map.get(d)]


def derived_spread(left, right, factor):
    """週次のleftに対し、同日以前の直近のright値を使って left*factor - right を返す。"""
    out = []
    j = -1
    for d, v in left:
        while j + 1 < len(right) and right[j + 1][0] <= d:
            j += 1
        if j >= 0:
            out.append((d, round(v * factor - right[j][1], 3)))
    return out


def downsample(series, limit=MAX_HISTORY_POINTS):
    if len(series) <= limit:
        return [list(p) for p in series]
    step = (len(series) - 1) / (limit - 1)
    idx = sorted({round(i * step) for i in range(limit)} | {len(series) - 1})
    return [list(series[i]) for i in idx]


def summarize(series):
    values = [v for _, v in series]
    latest_date, latest_value = series[-1]
    ordered = sorted(values)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    percentile = round(100 * sum(1 for v in values if v <= latest_value) / n, 1)
    return {
        "latest": {"date": latest_date, "value": round(latest_value, 4)},
        "stats": {"min": round(ordered[0], 4), "max": round(ordered[-1], 4),
                  "median": round(median, 4), "percentile": percentile,
                  "count": n, "start": series[0][0]},
        "history": downsample(series),
    }


def _public(spec):
    keys = ("id", "group", "name", "definition", "reading", "caution", "source",
            "source_url", "frequency", "unit", "formula")
    return {k: spec[k] for k in keys}


RESTRICTED_REASON = "第三者(指数提供元/データ配信元)の再配布制限があるため、公開リポジトリでは値・履歴を掲載しません。出典リンク先で確認してください。"
LOCAL_RESTRICTED_REASON = "ローカル専用データです。公開版への再配布はできません。"


def build_indicator(spec, series=None, error=None, allow_restricted=False):
    item = _public(spec)
    if spec.get("restricted") and not allow_restricted:
        item.update({"status": "restricted", "reason": RESTRICTED_REASON})
    elif series:
        item.update({"status": "ok", "reason": ""})
        item.update(summarize(series))
        if spec.get("restricted"):
            item["caution"] += " " + LOCAL_RESTRICTED_REASON
    elif spec["kind"] == "link":
        item.update({"status": "link_only", "reason": spec["reason"]})
    elif spec["kind"] == "pending":
        item.update({"status": "pending", "reason": spec["reason"]})
    else:
        item.update({"status": "unavailable", "reason": error or spec["reason"] or "取得に失敗しました。"})
    return item


def generate(fred=fetch_fred, eia=fetch_eia, yf_close=_yf_close, now=None, allow_restricted=False):
    cache = {}
    results = {}
    errors = {}

    def fred_cached(sid):
        if sid not in cache:
            cache[sid] = fred(sid)
        return cache[sid]

    for spec in SPECS:
        kind, p = spec["kind"], spec["params"]
        if spec.get("restricted") and not allow_restricted:
            continue
        try:
            if kind == "fred":
                results[spec["id"]] = fred_cached(p["series"])
            elif kind == "eia":
                results[spec["id"]] = eia(p)
            elif kind == "yf_momentum":
                results[spec["id"]] = moving_average_deviation(yf_close(p["ticker"]), p["window"])
            elif kind == "yf_ratio":
                results[spec["id"]] = ratio_series(yf_close(p["numerator"]), yf_close(p["denominator"]))
        except Exception as exc:
            # 例外文にURLやキーが含まれ得るため、型名のみ記録する
            errors[spec["id"]] = f"取得に失敗しました ({type(exc).__name__})。"
            if kind == "eia" and "EIA_API_KEY" in str(exc):
                errors[spec["id"]] = spec["reason"]

    for spec in SPECS:
        if spec["kind"] == "derived" and (allow_restricted or not spec.get("restricted")):
            p = spec["params"]
            if p["left"] in results and p["right"] in results:
                results[spec["id"]] = derived_spread(results[p["left"]], results[p["right"]], p["factor"])
            else:
                errors[spec["id"]] = "元データの取得に失敗したため算出できません。"

    generated = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "generated_at": generated,
        "groups": GROUPS,
        "indicators": [build_indicator(s, results.get(s["id"]), errors.get(s["id"]), allow_restricted)
                       for s in SPECS],
    }


def load_dotenv(path):
    """Load simple KEY=VALUE entries without overriding already-set environment variables."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch US market overview indicators.")
    parser.add_argument("--local", action="store_true",
                        help="include restricted series and write gitignored macro.local.json")
    args = parser.parse_args(argv)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(base_dir, ".env"))
    output_name = "macro.local.json" if args.local else "macro.json"
    out_path = os.path.join(base_dir, output_name)
    data = generate(allow_restricted=args.local)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    counts = {}
    for i in data["indicators"]:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    print(f"{output_name} written:", counts)


if __name__ == "__main__":
    main()
