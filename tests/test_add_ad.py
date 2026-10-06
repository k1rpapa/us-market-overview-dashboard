import csv
import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

import add_ad


class AddAdTests(unittest.TestCase):
    def test_parse_entry_defaults_and_validation(self):
        self.assertEqual(add_ad.parse_entry("nyse", "1500", "1700", today=date(2026, 10, 6)),
                         ("2026-10-06", "NYSE", 1500, 1700, 0, False))
        self.assertEqual(add_ad.parse_entry("nasdaq", "1", "2", "3", "2026-10-05",
                                            today=date(2026, 10, 6), unchanged_known=True),
                         ("2026-10-05", "NASDAQ", 1, 2, 3, True))
        bad = [
            ("UNKNOWN", "1", "1", "0", None),
            ("NYSE", "-1", "1", "0", None),
            ("NYSE", "1.5", "1", "0", None),
            ("NYSE", "1", "bad", "0", None),
            ("NYSE", "1", "1", "-1", None),
            ("NYSE", "1", "1", "0", "2026-02-30"),
            ("NYSE", "1", "1", "0", "2026-10-07"),
        ]
        for market, adv, dec, unchanged, day in bad:
            with self.subTest(market=market, adv=adv, date=day), self.assertRaises(ValueError):
                add_ad.parse_entry(market, adv, dec, unchanged, day, today=date(2026, 10, 6))

    def test_upsert_creates_header_and_replaces_only_same_market_day(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "local_data", "ad_issues.csv")
            self.assertEqual(add_ad.upsert(path, "2026-10-05", "NYSE", 1500, 1700, 100, True), 1)
            self.assertEqual(add_ad.upsert(path, "2026-10-05", "NASDAQ", 2000, 1000, 20, False), 2)
            self.assertEqual(add_ad.upsert(path, "2026-10-05", "NYSE", 1600, 1650, 50, True), 2)
            with open(path, encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["date", "universe", "advances", "declines", "unchanged", "unchanged_known"])
            self.assertEqual(rows[1:], [
                ["2026-10-05", "NASDAQ", "2000", "1000", "20", "0"],
                ["2026-10-05", "NYSE", "1600", "1650", "50", "1"],
            ])
            with open(path, encoding="utf-8") as handle:
                market, series = __import__("fetch_macro").parse_ad_csv(handle.read(), "NYSE")
            self.assertEqual((market, series), ("NYSE", [("2026-10-05", -50.0)]))

    def test_upsert_accepts_optional_unchanged_column_and_rejects_corrupt_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "ad_issues.csv")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write("date,market,advances,declines\n2026-10-04,NYSE,10,8\n")
            self.assertEqual(add_ad.upsert(path, "2026-10-05", "NYSE", 12, 9, 1, True), 2)
            with open(path, encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["unchanged"], "0")
            self.assertEqual(rows[0]["unchanged_known"], "0")
            rows[0]["advances"] = "bad"
            with open(path, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "invalid A/D CSV row"):
                add_ad.upsert(path, "2026-10-06", "NYSE", 10, 10, 0, False)

    def test_five_universes_coexist_for_same_date(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "local_data", "ad_issues.csv")
            for universe in add_ad.UNIVERSES:
                add_ad.upsert(path, "2026-10-05", universe, 100, 80, 20, True)
            with open(path, encoding="utf-8") as handle:
                import fetch_macro as fm
                rows = fm.read_ad_universes(path)
            self.assertEqual(set(rows), set(add_ad.UNIVERSES))
            self.assertTrue(all(records[0][0] == "2026-10-05" for records in rows.values()))

    def test_cli_accepts_past_date_and_marks_omitted_unchanged_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "ad_issues.csv")
            with patch.dict(os.environ, {"AD_ISSUES_CSV": path}):
                self.assertEqual(add_ad.main([
                    "--universe", "SP500", "--adv", "300", "--dec", "190",
                    "--date", "2026-10-05"
                ]), 0)
            with open(path, encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["date"], "2026-10-05")
            self.assertEqual(row["universe"], "SP500")
            self.assertEqual(row["unchanged"], "0")
            self.assertEqual(row["unchanged_known"], "0")


if __name__ == "__main__":
    unittest.main()
