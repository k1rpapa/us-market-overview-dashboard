import json
import os
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

        return fm.generate(fred=fred, eia=eia or no_eia, yf_close=yf_close or no_yf,
                           now=datetime(2026, 1, 1, tzinfo=timezone.utc))

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
        self.assertEqual(ids["cape"]["status"], "pending")
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
            self.assertIn(ind["status"], ("ok", "pending", "link_only", "unavailable", "restricted"))
            self.assertEqual(ind["status"] == "ok", "latest" in ind)
            self.assertTrue(ind["source"] and ind["definition"] and ind["frequency"])


if __name__ == "__main__":
    unittest.main()
