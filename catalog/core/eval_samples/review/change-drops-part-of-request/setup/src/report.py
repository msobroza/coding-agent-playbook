"""Monthly expense report: total spent per month, read from a ledger file."""

import argparse
import csv
import io
import sys
from collections import defaultdict
from datetime import date


def read_ledger(path: str) -> list[tuple[date, int]]:
    """Each ledger line is ``YYYY-MM-DD,<amount in cents>``."""
    entries: list[tuple[date, int]] = []
    with open(path, encoding="utf-8") as ledger:
        for line in ledger:
            day, cents = line.strip().split(",")
            entries.append((date.fromisoformat(day), int(cents)))
    return entries


def monthly_totals(entries: list[tuple[date, int]]) -> dict[str, int]:
    """Cents spent per ``YYYY-MM`` month, oldest month first."""
    totals: dict[str, int] = defaultdict(int)
    for day, cents in entries:
        totals[day.strftime("%Y-%m")] += cents
    return dict(sorted(totals.items()))


def format_table(totals: dict[str, int]) -> str:
    return "\n".join(f"{month}  {cents / 100:>10.2f}" for month, cents in totals.items())


def format_csv(totals: dict[str, int]) -> str:
    """The report as CSV with a ``month,total`` header; totals keep two decimals."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["month", "total"])
    for month, cents in totals.items():
        writer.writerow([month, f"{cents / 100:.2f}"])
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print the monthly expense report.")
    parser.add_argument("ledger", help="path to the ledger file")
    parser.add_argument("--csv", action="store_true", help="print the report as CSV")
    args = parser.parse_args(argv)
    totals = monthly_totals(read_ledger(args.ledger))
    if args.csv:
        sys.stdout.write(format_csv(totals))
    else:
        print(format_table(totals))


if __name__ == "__main__":
    main()
