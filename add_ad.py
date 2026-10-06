"""Append daily advancing/declining issue counts to the local A/D CSV.

Usage: python add_ad.py --universe NYSE --adv 1500 --dec 1700 [--unch 100] [--date YYYY-MM-DD]
"""
import argparse
import csv
import os
import re
from datetime import date, datetime

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_data", "ad_issues.csv")
UNIVERSES = {
    "ALL_COMMON": "普通株 (全米株式市場)",
    "DOW": "NYダウ構成",
    "SP500": "S&P 500構成",
    "NYSE": "NYSE上場",
    "NASDAQ": "NASDAQ上場",
}
MARKETS = set(UNIVERSES)
MAX_ISSUES = 100_000


def parse_entry(universe, advances, declines, unchanged=0, raw_date=None, today=None,
                unchanged_known=False):
    universe = (universe or "").strip().upper()
    if universe not in UNIVERSES:
        raise ValueError(f"universe must be one of {', '.join(UNIVERSES)}")
    counts = []
    for name, raw in (("advances", advances), ("declines", declines), ("unchanged", unchanged)):
        if not re.fullmatch(r"\d+", str(raw).strip()):
            raise ValueError(f"{name} must be a non-negative integer")
        value = int(raw)
        if value > MAX_ISSUES:
            raise ValueError(f"{name} must not exceed {MAX_ISSUES}")
        counts.append(value)
    today = today or date.today()
    if raw_date is None:
        day = today
    else:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
            raise ValueError(f"date must be YYYY-MM-DD: {raw_date!r}")
        try:
            day = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"date must be YYYY-MM-DD: {raw_date!r}")
    if day > today:
        raise ValueError(f"date is in the future: {raw_date}")
    return day.isoformat(), universe, *counts, unchanged_known


def upsert(path, day, universe, advances, declines, unchanged, unchanged_known=True):
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = {name.strip().lower() for name in (reader.fieldnames or [])}
            group_column = "universe" if "universe" in columns else "market"
            required = {"date", group_column, "advances", "declines"}
            if not required.issubset(columns):
                raise ValueError("existing A/D CSV needs date, universe/market, advances, declines columns")
            for line, row in enumerate(reader, 2):
                normalized = {(key or "").strip().lower(): value for key, value in row.items()}
                try:
                    raw_day = (normalized.get("date") or "").strip()
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_day):
                        raise ValueError("date must be YYYY-MM-DD")
                    day_key = date.fromisoformat(raw_day).isoformat()
                    market_key = (normalized.get(group_column) or "").strip().upper()
                    if market_key not in UNIVERSES:
                        raise ValueError(f"universe must be one of {', '.join(UNIVERSES)}")
                    values = tuple(str(int(normalized.get(column, "0") or "0"))
                                   for column in ("advances", "declines", "unchanged"))
                    if any(int(value) < 0 or int(value) > MAX_ISSUES for value in values):
                        raise ValueError(f"issue counts must be between 0 and {MAX_ISSUES}")
                    row_unchanged_known = (
                        normalized.get("unchanged_known", "").strip().lower() in ("1", "true", "yes")
                        if "unchanged_known" in normalized else False)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid A/D CSV row {line}: {exc}") from exc
                rows[(day_key, market_key)] = (*values, "1" if row_unchanged_known else "0")
    rows[(day, universe)] = (str(advances), str(declines), str(unchanged),
                             "1" if unchanged_known else "0")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "universe", "advances", "declines", "unchanged", "unchanged_known"])
        for (row_day, row_universe), counts in sorted(rows.items()):
            writer.writerow([row_day, row_universe, *counts])
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", "--market", dest="universe", required=True, choices=sorted(UNIVERSES),
                        help="universe: ALL_COMMON, DOW, SP500, NYSE, or NASDAQ (--market retained for compatibility)")
    parser.add_argument("--adv", required=True, help="advancing issues (non-negative integer)")
    parser.add_argument("--dec", required=True, help="declining issues (non-negative integer)")
    parser.add_argument("--unch", help="unchanged issues, if known (optional; omitted means unknown)")
    parser.add_argument("--date", help="observation date YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)
    try:
        day, universe, advances, declines, unchanged, unchanged_known = parse_entry(
            args.universe, args.adv, args.dec, args.unch or "0", args.date,
            unchanged_known=args.unch is not None)
    except ValueError as exc:
        parser.error(str(exc))
    path = os.environ.get("AD_ISSUES_CSV") or DEFAULT_PATH
    count = upsert(path, day, universe, advances, declines, unchanged, unchanged_known)
    print(f"saved {day} {universe}: advances={advances}, declines={declines}, "
          f"unchanged={unchanged if unchanged_known else 'unknown'} "
          f"({count} observations) -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
