"""Append daily advancing/declining issue counts to the local A/D CSV.

Usage: python add_ad.py --market NYSE --adv 1500 --dec 1700 [--unch 100] [--date YYYY-MM-DD]
"""
import argparse
import csv
import os
import re
from datetime import date, datetime

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_data", "ad_issues.csv")
MARKETS = {"NYSE", "NASDAQ"}
MAX_ISSUES = 100_000


def parse_entry(market, advances, declines, unchanged=0, raw_date=None, today=None):
    market = (market or "").strip().upper()
    if market not in MARKETS:
        raise ValueError(f"market must be one of {', '.join(sorted(MARKETS))}")
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
    return day.isoformat(), market, *counts


def upsert(path, day, market, advances, declines, unchanged):
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = {name.strip().lower() for name in (reader.fieldnames or [])}
            required = {"date", "market", "advances", "declines"}
            if not required.issubset(columns):
                raise ValueError("existing A/D CSV needs date, market, advances, declines columns")
            for line, row in enumerate(reader, 2):
                normalized = {(key or "").strip().lower(): value for key, value in row.items()}
                try:
                    raw_day = (normalized.get("date") or "").strip()
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_day):
                        raise ValueError("date must be YYYY-MM-DD")
                    day_key = date.fromisoformat(raw_day).isoformat()
                    market_key = (normalized.get("market") or "").strip().upper()
                    if market_key not in MARKETS:
                        raise ValueError("market must be NYSE or NASDAQ")
                    values = tuple(str(int(normalized.get(column, "0") or "0"))
                                   for column in ("advances", "declines", "unchanged"))
                    if any(int(value) < 0 or int(value) > MAX_ISSUES for value in values):
                        raise ValueError(f"issue counts must be between 0 and {MAX_ISSUES}")
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid A/D CSV row {line}: {exc}") from exc
                rows[(day_key, market_key)] = values
    rows[(day, market)] = (str(advances), str(declines), str(unchanged))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "market", "advances", "declines", "unchanged"])
        for (row_day, row_market), counts in sorted(rows.items()):
            writer.writerow([row_day, row_market, *counts])
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True, choices=sorted(MARKETS))
    parser.add_argument("--adv", required=True, help="advancing issues (non-negative integer)")
    parser.add_argument("--dec", required=True, help="declining issues (non-negative integer)")
    parser.add_argument("--unch", default="0", help="unchanged issues (default: 0)")
    parser.add_argument("--date", help="observation date YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)
    try:
        day, market, advances, declines, unchanged = parse_entry(
            args.market, args.adv, args.dec, args.unch, args.date)
    except ValueError as exc:
        parser.error(str(exc))
    path = os.environ.get("AD_ISSUES_CSV") or DEFAULT_PATH
    count = upsert(path, day, market, advances, declines, unchanged)
    print(f"saved {day} {market}: advances={advances}, declines={declines}, unchanged={unchanged} "
          f"({count} observations) -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
