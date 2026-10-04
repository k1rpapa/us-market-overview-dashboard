"""Append one day's Barchart $CPCS close to the local, gitignored CSV.

Usage: python add_putcall.py 0.62 [YYYY-MM-DD]   (date defaults to today)
"""
import csv
import math
import os
import sys
from datetime import date, datetime

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_data", "barchart_cpcs.csv")
MAX_RATIO = 10.0


def parse_entry(raw_value, raw_date=None, today=None):
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid value: {raw_value!r}")
    if not math.isfinite(value) or not 0 < value <= MAX_RATIO:
        raise ValueError(f"value must be between 0 and {MAX_RATIO}: {raw_value!r}")
    today = today or date.today()
    if raw_date is None:
        day = today
    else:
        try:
            day = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"date must be YYYY-MM-DD: {raw_date!r}")
    if day > today:
        raise ValueError(f"date is in the future: {raw_date}")
    return day.isoformat(), value


def upsert(path, day, value):
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                rows[(row.get("Date") or "").strip()] = (row.get("Close") or "").strip()
    rows.pop("", None)
    rows[day] = repr(value)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Close"])
        for key in sorted(rows):
            writer.writerow([key, rows[key]])
    return len(rows)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not 1 <= len(args) <= 2:
        print(__doc__)
        return 2
    path = os.environ.get("BARCHART_CPCS_CSV") or DEFAULT_PATH
    try:
        day, value = parse_entry(args[0], args[1] if len(args) == 2 else None)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    count = upsert(path, day, value)
    print(f"saved {day} = {value} ({count} days accumulated) -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
