import json, unittest
import insights as I

def mk(local=False):
    return {"local_only": local, "groups": [{"id": "g1", "name": "信用"}, {"id": "g2", "name": "景気"}],
        "indicators": [
        {"id": "a", "group": "g1", "name": "HY OAS", "status": "ok", "restricted": True, "latest": {"date": "2026-01-01", "value": 3.1}, "stats": {"count": 500, "percentile": 40}},
        {"id": "b", "group": "g1", "name": "NFCI", "status": "ok", "latest": {"date": "2026-01-01", "value": -0.5}, "stats": {"count": 500, "percentile": 20}},
        {"id": "c", "group": "g1", "name": "Margin", "status": "stale", "latest": {"date": "2020-01-01", "value": 1}, "stats": {"count": 5}},
        {"id": "d", "group": "g2", "name": "X", "status": "pending", "reason": "no"}]}

class T(unittest.TestCase):
    def test_public_excludes_restricted(self):
        c = I.build_category_inputs(mk(), False)
        s = json.dumps(c, ensure_ascii=False)
        self.assertNotIn("HY OAS", s); self.assertNotIn("3.1", s)
        self.assertIn("NFCI", s)

    def test_public_ad_values_excluded_from_prompt_and_output(self):
        data = mk()
        for index, universe in enumerate(("all_common", "dow", "sp500", "nyse", "nasdaq")):
            data["indicators"].append({
                "id": "ad_line_" + universe, "group": "g1", "name": "A/D line",
                "status": "restricted", "restricted": True,
                "latest": {"date": "2026-10-05", "value": 12345 + index},
                "history": [["2026-10-04", 10000], ["2026-10-05", 12345 + index]],
                "breadth": {"advance_pct": 72.5},
                "comparison": {"reading": "上昇の広がりが弱まる可能性を示唆します。"},
            })
        calls = []

        def post(url, body, key):
            calls.append(body)
            return {"candidates": [{"content": {"parts": [{"text": "市場の上昇を確認"}]}}]}

        out = I.generate_insights(data, api_key="k", post=post)
        for value in range(12345, 12350):
            self.assertNotIn(str(value), json.dumps(calls, ensure_ascii=False))
            self.assertNotIn(str(value), json.dumps(out, ensure_ascii=False))
        self.assertNotIn("示唆", json.dumps(calls, ensure_ascii=False))
        self.assertNotIn("示唆", json.dumps(out, ensure_ascii=False))

    def test_public_rejects_local_data(self):
        with self.assertRaises(ValueError):
            I.build_category_inputs(mk(True), False)

    def test_local_includes_restricted(self):
        self.assertIn("HY OAS", json.dumps(I.build_category_inputs(mk(True), True), ensure_ascii=False))

    def test_short_history_no_percentile(self):
        item = I.indicator_input(mk()["indicators"][2])
        self.assertNotIn("percentile_in_history", item)

    def test_no_key_unavailable(self):
        out = I.generate_insights(mk(), api_key=None)
        self.assertEqual(out["categories"]["g1"]["status"], "unavailable")
        self.assertEqual(out["categories"]["g2"]["status"], "unavailable")
        self.assertIsNone(out["summary"])

    def test_generation_and_cache(self):
        calls = []
        def post(url, body, key):
            calls.append(body)
            return {"candidates": [{"content": {"parts": [{"text": "分析文"}]}}]}
        out = I.generate_insights(mk(), api_key="k", post=post)
        self.assertEqual(out["categories"]["g1"]["text"], "分析文")
        self.assertEqual(out["categories"]["g2"]["status"], "unavailable")
        self.assertEqual(len(calls), 2)  # g1 + summary
        self.assertNotIn("3.1", json.dumps(calls[0], ensure_ascii=False))
        self.assertEqual(calls[0]["generationConfig"]["temperature"], 0.2)
        calls.clear()
        I.generate_insights(mk(), previous=out, api_key="k", post=post)
        self.assertEqual(calls, [])

    def test_failure_fallback_hides_key(self):
        def post(url, body, key):
            raise RuntimeError("secret-key in url")
        out = I.generate_insights(mk(), api_key="secret-key", post=post)
        self.assertEqual(out["categories"]["g1"]["status"], "unavailable")
        self.assertNotIn("secret-key", json.dumps(out, ensure_ascii=False))

    def test_public_output_with_restricted_terms_rejected(self):
        post = lambda u, b, k: {"candidates": [{"content": {"parts": [{"text": "HY OASは3.1"}]}}]}
        out = I.generate_insights(mk(), api_key="k", post=post)
        self.assertEqual(out["categories"]["g1"]["status"], "unavailable")
        post = lambda u, b, k: {"candidates": [{"content": {"parts": [{"text": "A/Dの上昇の広がりが弱まる可能性を示唆"}]}}]}
        out = I.generate_insights(mk(), api_key="k", post=post)
        self.assertEqual(out["categories"]["g1"]["status"], "unavailable")
        out = I.generate_insights(mk(True), api_key="k", post=post, allow_restricted=True)
        self.assertEqual(out["categories"]["g1"]["status"], "ok")


    def test_default_model_fallback_order(self):
        attempts = []
        def post(url, body, key):
            attempts.append(url)
            if len(attempts) == 1:
                raise RuntimeError("model unavailable")
            return {"candidates": [{"content": {"parts": [{"text": "analysis"}]}}]}
        text, model = I.call_gemini("system", "user", "key", I.DEFAULT_MODELS, post)
        self.assertEqual(model, "gemini-2.5-flash")
        self.assertEqual([u.rsplit("/", 1)[-1].split(":", 1)[0] for u in attempts],
                         ["gemini-3.8-flash", "gemini-2.5-flash"])
if __name__ == "__main__":
    unittest.main()