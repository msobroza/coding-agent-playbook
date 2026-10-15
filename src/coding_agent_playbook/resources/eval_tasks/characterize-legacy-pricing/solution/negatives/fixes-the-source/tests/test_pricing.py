"""Tests for src/pricing.py, matching the documented bulk discount."""

from pathlib import Path

import pytest
from src import pricing
from src.pricing import apply_coupon, line_total, order_total


@pytest.fixture(autouse=True)
def audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the audit file order_total appends to, so no test writes into the repo."""
    log_path = tmp_path / "pricing_audit.log"
    monkeypatch.setattr(pricing, "AUDIT_LOG", str(log_path))
    return log_path


def test_line_total_below_bulk_pays_full_price() -> None:
    assert line_total(100, 9) == 900


def test_line_total_takes_the_bulk_discount_from_ten_units() -> None:
    assert line_total(100, 10) == 900


def test_apply_coupon_half() -> None:
    assert apply_coupon(1000, "HALF") == 500


def test_order_total_adds_shipping_below_the_threshold() -> None:
    assert order_total([(1000, 2)]) == 2499
