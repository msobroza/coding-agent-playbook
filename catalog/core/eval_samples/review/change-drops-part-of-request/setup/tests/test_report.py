from datetime import date
from pathlib import Path

import pytest

from src.report import format_csv, format_table, main, monthly_totals


def test_monthly_totals_groups_by_month_oldest_first() -> None:
    entries = [(date(2024, 2, 3), 500), (date(2024, 1, 9), 250), (date(2024, 2, 20), 125)]
    assert monthly_totals(entries) == {"2024-01": 250, "2024-02": 625}


def test_format_table_prints_one_line_per_month() -> None:
    assert format_table({"2024-01": 250}) == "2024-01        2.50"


def test_format_csv_writes_a_header_and_one_row_per_month() -> None:
    assert format_csv({"2024-01": 250, "2024-02": 1005}) == (
        "month,total\n2024-01,2.50\n2024-02,10.05\n"
    )


def test_main_prints_csv_with_the_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("2024-01-09,250\n2024-01-20,100\n", encoding="utf-8")
    main([str(ledger), "--csv"])
    assert capsys.readouterr().out == "month,total\n2024-01,3.50\n"
