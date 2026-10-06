import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

import fetch_macro as fm

FRED_CSV = "observation_date,X\n2024-01-01,1.5\n2024-01-02,.\n2024-01-03,2.5\n"


class SummaryTests(unittest.TestCase):
    def test_parse_fred_skips_missing(self):
        self.assertEqual(fm.parse_fred_csv(FRED_CSV), [("2024-01-01", 1.5), ("2024-01-03", 2.5)])

    def test_summarize_percentile_and_downsample(self):
        series = [(f"2000-{i:05d}", float(i)) for i in range(1000)]
        s = fm.summarize(series)
        self.assertEqual(s["latest"]["value"], 999.0)
        self.assertEqual(s["stats"]["percentile"], 100.0)
        self.assertLessEqual(len(s["history"]), fm.MAX_HISTORY_POINTS + 1)
        self.assertEqual(s["history"][-1][0], series[-1][0])

    def test_moving_average_deviation(self):
        out = fm.moving_average_deviation([("a", 1.0), ("b", 3.0), ("c", 5.0)], 2)
        self.assertEqual(out, [("b", 50.0), ("c", 25.0)])

    def test_derived_spread_uses_prior_right_value(self):
        out = fm.derived_spread([("2024-01-08", 2.0)], [("2024-01-05", 50.0), ("2024-01-09", 99.0)], 42)
        self.assertEqual(out, [("2024-01-08", 34.0)])


class GenerateTests(unittest.TestCase):
    def run_generate(self, fred, eia=None, yf_close=None):
        def no_eia(_):
            raise RuntimeError("EIA_API_KEY not set")

        def no_yf(_):
            raise RuntimeError("down")

        def unavailable(*_args, **_kwargs):
            raise RuntimeError("offline fixture")

        return fm.generate(fred=fred, eia=eia or no_eia, yf_close=yf_close or no_yf,
                           now=datetime(2026, 1, 1, tzinfo=timezone.utc),
                           shiller=unavailable, finra=unavailable, acm=unavailable,
                           cot=unavailable, nyfed_hhdc=unavailable, recession=unavailable,
                           cboe=unavailable)

    def by_id(self, data):
        return {i["id"]: i for i in data["indicators"]}

    def test_all_indicators_present_and_failures_are_explicit(self):
        def fred(_):
            raise OSError("https://x?api_key=SECRET")

        data = self.run_generate(fred)
        ids = self.by_id(data)
        self.assertEqual(len(ids), len(fm.SPECS))
        for ind in ids.values():
            self.assertNotIn("latest", ind)
            self.assertNotIn("history", ind)
        self.assertEqual(ids["nfci"]["status"], "unavailable")
        self.assertEqual(ids["cape"]["status"], "unavailable")
        self.assertEqual(ids["fear_greed"]["status"], "link_only")
        self.assertEqual(ids["distillate_stocks"]["status"], "unavailable")
        self.assertEqual(ids["diesel_crude_spread"]["status"], "unavailable")
        self.assertNotIn("SECRET", json.dumps(data))

    def test_successful_series_and_derived(self):
        def fred(sid):
            return {"GASDESW": [("2024-01-08", 3.0)], "DCOILWTICO": [("2024-01-05", 70.0)]}.get(
                sid, [("2024-01-01", 1.0), ("2024-01-02", 2.0)])

        ids = self.by_id(self.run_generate(fred))
        self.assertEqual(ids["nfci"]["status"], "ok")
        self.assertEqual(ids["nfci"]["latest"]["value"], 2.0)
        for rid in ("hy_oas", "ig_oas", "sp500_200d", "cap_vs_equal", "vix_curve"):
            self.assertEqual(ids[rid]["status"], "restricted")
            self.assertNotIn("latest", ids[rid])
            self.assertNotIn("history", ids[rid])
        self.assertEqual(ids["diesel_crude_spread"]["latest"]["value"], 56.0)

    def test_local_mode_includes_restricted_series(self):
        def fred(_):
            return [("2024-01-01", 1.0), ("2024-01-02", 2.0)]

        def yf_close(_):
            return [(f"2024-{i:03d}", float(i + 100)) for i in range(220)]

        def unavailable(*_args, **_kwargs):
            raise RuntimeError("offline fixture")

        ids = self.by_id(fm.generate(fred=fred, eia=lambda _: [], yf_close=yf_close, allow_restricted=True,
                                     shiller=unavailable, finra=unavailable, acm=unavailable,
                                     cot=unavailable, nyfed_hhdc=unavailable, recession=unavailable,
                                     cboe=lambda: [("2026-01-01", 0.9)],
                                     now=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        for rid in ("hy_oas", "ig_oas", "sp500_200d", "cap_vs_equal", "vix_curve"):
            self.assertEqual(ids[rid]["status"], "ok")
            self.assertIn("latest", ids[rid])
            self.assertIn("history", ids[rid])
        self.assertIn("ローカル専用", ids["hy_oas"]["caution"])
        self.assertEqual(ids["put_call"]["status"], "ok")

    def test_new_public_sources_are_wired(self):
        series = [("2026-08-01", 2.0), ("2026-08-31", 2.5)]
        data = fm.generate(
            fred=lambda sid: series,
            eia=lambda _: series,
            yf_close=lambda _: [(f"2026-{i:03d}", float(i + 100)) for i in range(220)],
            shiller=lambda: [("2026-08-01", 25.0)],
            finra=lambda: [("2026-08-01", 100000.0)],
            acm=lambda: [("2026-08-31", 0.5)],
            cot=lambda _: [("2026-08-25", 12.5)],
            nyfed_hhdc=lambda p, **_: [("2026-04-01", 8.0 if p["column"] == "CC" else 7.0)],
            recession=lambda: [("2026-08-31", 5.0)],
            cboe=lambda: [("2026-08-31", 0.9)],
            now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        ids = self.by_id(data)
        for indicator_id in ("cape", "erp", "margin_debt", "cot_sp500", "term_premium",
                             "recession_prob", "card_delinq", "auto_delinq",
                             "card_serious_delinq", "auto_serious_delinq"):
            self.assertEqual(ids[indicator_id]["status"], "ok", indicator_id)
            self.assertIn("latest", ids[indicator_id])

    def test_dotenv_does_not_override_existing_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".env")
            with open(path, "w", encoding="utf-8") as f:
                f.write("DASH_TEST_ENV=from-file\n")
            os.environ["DASH_TEST_ENV"] = "from-process"
            try:
                fm.load_dotenv(path)
                self.assertEqual(os.environ["DASH_TEST_ENV"], "from-process")
            finally:
                del os.environ["DASH_TEST_ENV"]

    def test_cape_erp_monthly_join(self):
        cape = [("2024-01-01", 25.0), ("2024-02-01", 20.0)]
        real_yield = [("2024-01-12", 1.5), ("2024-01-31", 2.0), ("2024-02-29", 2.5)]
        self.assertEqual(fm.cape_erp(cape, real_yield), [("2024-01-01", 2.0), ("2024-02-01", 2.5)])

    def test_parse_nyfed_hhdc_quarterly_series(self):
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Page 13 Data"
        sheet.append(["New Delinquent Balances"])
        sheet.append(["Percent"])
        sheet.append(["Return"])
        sheet.append([None, "AUTO", "CC"])
        sheet.append(["26:Q1", 7.72, 8.61])
        sheet.append(["26:Q2", 7.87, 8.69])
        stream = tempfile.SpooledTemporaryFile()
        workbook.save(stream)
        stream.seek(0)
        data = stream.read()
        self.assertEqual(fm.parse_nyfed_hhdc_xlsx(data, "Page 13 Data", "CC"),
                         [("2026-03-31", 8.61), ("2026-06-30", 8.69)])

    def test_cot_net_leveraged_position_as_percent_of_open_interest(self):
        payload = json.dumps([{
            "report_date_as_yyyy_mm_dd": "2026-09-29T00:00:00.000",
            "open_interest_all": "1000",
            "lev_money_positions_long": "350",
            "lev_money_positions_short": "450",
        }])
        series = fm.fetch_cot({"market": "S&P 500 Consolidated"}, http_get=lambda *_a, **_k: payload)
        self.assertEqual(series, [("2026-09-29", -10.0)])

    def test_nyfed_recession_probability_parses_centuries_and_percent(self):
        payload = "Date,Rec_prob\n31-May-61,12.35%\n31-Aug-26,5.80%\n"
        series = fm.fetch_nyfed_recession(http_get=lambda *_a, **_k: payload)
        self.assertEqual(series, [("1961-05-31", 12.35), ("2026-08-31", 5.8)])

    def test_cboe_put_call_csv_skips_disclaimer_and_parses_history(self):
        payload = ("Disclaimer line,,,,\n, PRODUCT: TOTAL,,EXCHANGE: Cboe,\n"
                   "DATE,CALLS,PUTS,TOTAL,P/C Ratio\n"
                   "11/1/2006,1401036,1271445,2672481,0.91\n")
        series = fm.fetch_cboe_put_call(http_get=lambda *_a, **_k: payload)
        self.assertEqual(series, [("2006-11-01", 0.91)])

    def test_monthly_cape_is_marked_stale_but_keeps_observation(self):
        data = fm.generate(
            fred=lambda sid: [("2023-09-29", 2.0)] if sid == "DFII10" else (_ for _ in ()).throw(RuntimeError()),
            eia=lambda _: [], yf_close=lambda _: [], shiller=lambda: [("2023-09-01", 30.0)],
            finra=lambda: (_ for _ in ()).throw(RuntimeError()),
            acm=lambda: (_ for _ in ()).throw(RuntimeError()),
            cot=lambda _: (_ for _ in ()).throw(RuntimeError()),
            nyfed_hhdc=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError()),
            recession=lambda: (_ for _ in ()).throw(RuntimeError()),
            cboe=lambda: (_ for _ in ()).throw(RuntimeError()),
            now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        ids = self.by_id(data)
        self.assertEqual(ids["cape"]["status"], "stale")
        self.assertEqual(ids["cape"]["latest"]["date"], "2023-09-01")
        self.assertEqual(ids["erp"]["status"], "stale")
        self.assertEqual(ids["recession_prob"]["status"], "unavailable")

    def test_probit_proxy_matches_nyfed_formula(self):
        series = fm.recession_probit_proxy([("2026-01-02", 1.0), ("2026-01-30", 3.0), ("2026-02-27", -1.0)])
        self.assertEqual([d for d, _ in series], ["2026-01-30", "2026-02-27"])
        self.assertAlmostEqual(series[0][1], 3.6, delta=0.05)
        self.assertAlmostEqual(series[1][1], 54.0, delta=0.05)

    def test_stale_official_recession_csv_falls_back_to_labeled_proxy(self):
        data = fm.generate(
            fred=lambda sid: [("2026-09-01", 1.0), ("2026-09-30", 1.0)] if sid == "T10Y3M" else [],
            eia=lambda _: [], yf_close=lambda _: [],
            shiller=lambda: (_ for _ in ()).throw(RuntimeError()),
            finra=lambda: (_ for _ in ()).throw(RuntimeError()),
            acm=lambda: (_ for _ in ()).throw(RuntimeError()),
            cot=lambda _: (_ for _ in ()).throw(RuntimeError()),
            nyfed_hhdc=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError()),
            recession=lambda: [("2017-06-30", 8.11)],
            cboe=lambda: (_ for _ in ()).throw(RuntimeError()),
            now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        item = self.by_id(data)["recession_prob"]
        self.assertEqual(item["status"], "ok")
        self.assertEqual(item["latest"]["date"], "2026-09-30")
        self.assertIn("代理", item["name"])
        self.assertIn("0.6330", item["formula"])

    def test_shiller_page_link_is_extracted(self):
        html = '<a href="//img1.wsimg.com/blobby/go/x/downloads/y/ie_data.xls?ver=1">xls</a>'
        self.assertEqual(fm.shiller_workbook_url(html),
                         "https://img1.wsimg.com/blobby/go/x/downloads/y/ie_data.xls?ver=1")
        with self.assertRaises(ValueError):
            fm.shiller_workbook_url("<html></html>")

    def test_barchart_csv_parsing_and_local_priority(self):
        text = ('Time,Open,High,Low,Last,Change,%Change,Volume\n'
                '2026-10-01,0.6,0.7,0.5,0.62,0,0,0\n10/02/2026,0.6,0.7,0.5,"0.58",0,0,0\n'
                'Downloaded from Barchart.com as of 10-03-2026\n')
        self.assertEqual(fm.parse_barchart_csv(text), [("2026-10-01", 0.62), ("2026-10-02", 0.58)])
        with self.assertRaises(ValueError):
            fm.parse_barchart_csv("foo,bar\n1,2\n")
        self.assertIsNone(fm.read_barchart_cpcs(os.path.join(tempfile.gettempdir(), "missing-cpcs.csv")))
        series = fm.parse_barchart_csv(text)
        kwargs = dict(fred=lambda s: [], eia=lambda _: [], yf_close=lambda _: [],
                      shiller=lambda: [], finra=lambda: [], acm=lambda: [], cot=lambda _: [],
                      nyfed_hhdc=lambda *_a, **_k: [], recession=lambda: [],
                      cboe=lambda: [("2019-10-04", 1.05)], barchart=lambda: series,
                      now=datetime(2026, 10, 3, tzinfo=timezone.utc))
        local = self.by_id(fm.generate(allow_restricted=True, **kwargs))["put_call"]
        self.assertEqual(local["latest"]["date"], "2026-10-02")
        self.assertIn("$CPCS", local["name"])
        public = self.by_id(fm.generate(allow_restricted=False, **kwargs))["put_call"]
        self.assertEqual(public["status"], "restricted")
        self.assertNotIn("latest", public)

    def test_ad_line_cumulative_markets_stale_and_restricted(self):
        text = ('date,market,advances,declines,unchanged\n'
                '2026-10-01,NYSE,"1,500",1000,100\n2026-10-02,NYSE,800,1700,50\n'
                '2026-10-02,NASDAQ,2000,1000,0\n10/05/2026,NYSE,1200,1300,10\n')
        market, series = fm.parse_ad_csv(text)
        self.assertEqual(market, "NYSE")
        self.assertEqual(series, [("2026-10-01", 500.0), ("2026-10-02", -400.0), ("2026-10-05", -500.0)])
        self.assertEqual(fm.parse_ad_csv(text, "nasdaq"), ("NASDAQ", [("2026-10-02", 1000.0)]))
        with self.assertRaises(ValueError):
            fm.parse_ad_csv(text, "SP500")
        with self.assertRaises(ValueError):
            fm.parse_ad_csv("a,b\n1,2\n")
        self.assertIsNone(fm.read_ad_line(os.path.join(tempfile.gettempdir(), "missing-ad.csv")))
        kwargs = dict(fred=lambda s: [], eia=lambda _: [], yf_close=lambda _: [],
                      shiller=lambda: [], finra=lambda: [], acm=lambda: [], cot=lambda _: [],
                      nyfed_hhdc=lambda *_a, **_k: [], recession=lambda: [],
                      cboe=lambda: [], barchart=lambda: None, ad_reader=lambda: (market, series))
        local = self.by_id(fm.generate(allow_restricted=True, now=datetime(2026, 10, 6, tzinfo=timezone.utc), **kwargs))["ad_line"]
        self.assertEqual((local["status"], local["market"], local["latest"]["date"]), ("ok", "NYSE", "2026-10-05"))
        self.assertEqual(local["stats"]["count"], 3)
        stale = self.by_id(fm.generate(allow_restricted=True, now=datetime(2026, 10, 20, tzinfo=timezone.utc), **kwargs))["ad_line"]
        self.assertEqual(stale["status"], "stale")
        public = self.by_id(fm.generate(allow_restricted=False, **kwargs))["ad_line"]
        self.assertEqual(public["status"], "restricted")
        self.assertNotIn("latest", public)
        self.assertNotIn("market", public)
        missing = self.by_id(fm.generate(allow_restricted=True, **dict(kwargs, ad_reader=lambda: None)))["ad_line"]
        self.assertEqual(missing["status"], "unavailable")

    def test_ad_breadth_and_index_divergence_are_local_only(self):
        records = []
        cumulative = []
        value = 0
        for day in range(1, 12):
            adv, dec = (110, 100) if day < 11 else (50, 200)
            value += adv - dec
            records.append((f"2026-09-{day:02d}", adv, dec, 10))
            cumulative.append((f"2026-09-{day:02d}", value))
        index = [(f"2026-09-{day:02d}", float(100 + day)) for day in range(1, 11)]
        index.append(("2026-09-11", 120.0))
        kwargs = dict(fred=lambda s: [], eia=lambda _: [], yf_close=lambda ticker: index if ticker == "^NYA" else [],
                      shiller=lambda: [], finra=lambda: [], acm=lambda: [], cot=lambda _: [],
                      nyfed_hhdc=lambda *_a, **_k: [], recession=lambda: [],
                      cboe=lambda: [], barchart=lambda: None, ad_reader=lambda: ("NYSE", cumulative),
                      ad_records_reader=lambda: ("NYSE", records),
                      now=datetime(2026, 9, 11, tzinfo=timezone.utc))
        local = self.by_id(fm.generate(allow_restricted=True, **kwargs))["ad_line"]
        self.assertEqual(local["breadth"]["advance_pct"], 20.0)
        self.assertEqual(local["breadth"]["average_window"], 10)
        self.assertEqual(local["daily_net"][-1], ["2026-09-11", -150])
        self.assertIn("高値を更新", local["comparison"]["reading"])
        self.assertIn("可能性を示唆", local["comparison"]["reading"])
        self.assertEqual(local["comparison"]["ticker"], "^NYA")
        self.assertEqual(local["comparison"]["series"][0][1:], [0, 0.0])
        self.assertLess(local["comparison"]["series"][-1][1], 0)
        self.assertGreater(local["comparison"]["series"][-1][2], 0)
        public = self.by_id(fm.generate(allow_restricted=False, **kwargs))["ad_line"]
        self.assertEqual(public["status"], "restricted")
        for field in ("latest", "history", "breadth", "daily_net", "comparison"):
            self.assertNotIn(field, public)

    def test_add_putcall_appends_overwrites_and_rejects_bad_input(self):
        import add_putcall as ap
        today = datetime(2026, 10, 4).date()
        self.assertEqual(ap.parse_entry("0.62", None, today), ("2026-10-04", 0.62))
        for bad in (("abc", None), ("-1", None), ("nan", None), ("99", None), ("0.6", "2026-13-01"), ("0.6", "2026-10-05")):
            with self.assertRaises(ValueError):
                ap.parse_entry(*bad, today=today)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "local_data", "barchart_cpcs.csv")
            ap.upsert(path, "2026-10-03", 0.7)
            ap.upsert(path, "2026-10-02", 0.5)
            self.assertEqual(ap.upsert(path, "2026-10-03", 0.71), 2)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read().splitlines(), ["Date,Close", "2026-10-02,0.5", "2026-10-03,0.71"])
            self.assertEqual(fm.read_barchart_cpcs(path), [("2026-10-02", 0.5), ("2026-10-03", 0.71)])

    def test_eia_key_never_written(self):
        os.environ["EIA_API_KEY"] = "TOPSECRETKEY"
        try:
            def eia(_):
                raise OSError("GET https://api.eia.gov/?api_key=TOPSECRETKEY failed")

            data = self.run_generate(lambda s: [("2024-01-01", 1.0)], eia=eia)
            self.assertNotIn("TOPSECRETKEY", json.dumps(data))
        finally:
            del os.environ["EIA_API_KEY"]

    def test_committed_macro_json_schema(self):
        path = os.path.join(os.path.dirname(__file__), "..", "macro.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for ind in data["indicators"]:
            self.assertIn(ind["status"], ("ok", "stale", "pending", "link_only", "unavailable", "restricted"))
            self.assertIn(ind["status"], ("ok", "stale") if "latest" in ind else
                          ("pending", "link_only", "unavailable", "restricted"))
            self.assertTrue(ind["source"] and ind["definition"] and ind["frequency"])
        by_id = {ind["id"]: ind for ind in data["indicators"]}
        for indicator_id in ("hy_oas", "ig_oas", "sp500_200d", "cap_vs_equal", "vix_curve"):
            self.assertEqual(by_id[indicator_id]["status"], "restricted")
            self.assertNotIn("latest", by_id[indicator_id])
            self.assertNotIn("history", by_id[indicator_id])

    def test_local_file_is_ignored_and_pages_staging_is_allowlisted(self):
        root = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(root, ".gitignore"), encoding="utf-8") as f:
            self.assertIn("macro.local.json", f.read())
        with open(os.path.join(root, ".github", "workflows", "update-and-deploy.yml"), encoding="utf-8") as f:
            workflow = f.read()
        staging = workflow.split("Stage public files only", 1)[1].split("configure-pages", 1)[0]
        self.assertIn("macro.json", staging)
        self.assertNotIn("macro.local.json", staging)


if __name__ == "__main__":
    unittest.main()
