"""Characterization tests for src/pricing.py.

They pin what the module returns today, odd results included, so a refactor that
moves any amount fails here first. A ``*_currently_*`` test pins behavior that
looks wrong: it is recorded, not approved.
"""

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


@pytest.mark.parametrize(
    ("unit_cents", "quantity", "expected"),
    [
        (250, 1, 250),
        (250, 9, 2250),
        (100, 11, 990),  # 1100 - 10%
        (105, 11, 1040),  # 1155 - 10% = 1039.5, rounded half to even
        (250, 0, 0),
        (250, -3, 0),
    ],
    ids=["single", "below-bulk", "first-bulk", "bulk-rounds-up", "zero", "negative"],
)
def test_line_total(unit_cents: int, quantity: int, expected: int) -> None:
    assert line_total(unit_cents, quantity) == expected


def test_line_total_currently_charges_full_price_for_exactly_ten_units() -> None:
    # Pinned, not approved: the docstring promises the bulk discount from 10 units,
    # but the comparison is `>`, so 10 units still pay 10 * 250.
    assert line_total(250, 10) == 2500


def test_line_total_currently_rounds_a_half_cent_down_to_even() -> None:
    # Pinned, not approved: 1265 - 10% = 1138.5, and round() goes to the even 1138.
    assert line_total(115, 11) == 1138


@pytest.mark.parametrize(
    ("subtotal_cents", "coupon", "expected"),
    [
        (1000, None, 1000),
        (1000, "", 1000),
        (1000, "HALF", 500),
        (1000, "FLAT150", 850),
        (75, "HALF", 38),  # 37.5 rounds half to even
    ],
    ids=["none", "empty", "half", "flat", "half-rounds-up"],
)
def test_apply_coupon(subtotal_cents: int, coupon: str | None, expected: int) -> None:
    assert apply_coupon(subtotal_cents, coupon) == expected


def test_apply_coupon_currently_rounds_half_of_25_down_to_12() -> None:
    # Pinned, not approved: 12.5 rounds half to even, so the customer saves 13 cents.
    assert apply_coupon(25, "HALF") == 12


@pytest.mark.parametrize("coupon", ["half", "BOGUS"], ids=["lowercase", "unknown"])
def test_apply_coupon_currently_ignores_unrecognized_codes(coupon: str) -> None:
    # Pinned, not approved: codes are case-sensitive and unknown codes pass silently.
    assert apply_coupon(1000, coupon) == 1000


def test_apply_coupon_currently_allows_a_negative_subtotal() -> None:
    # Pinned, not approved: a flat amount larger than the subtotal is not capped.
    assert apply_coupon(300, "FLAT500") == -200


def test_apply_coupon_rejects_flat_without_an_amount() -> None:
    with pytest.raises(ValueError, match="invalid literal for int"):
        apply_coupon(1000, "FLAT")


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        ([(1000, 2)], 2499),  # 2000 + 499 shipping
        ([(1000, 5), (1, 1)], 5001),  # one cent over the threshold ships free
        ([(1000, 6)], 6000),
    ],
    ids=["pays-shipping", "just-over-threshold", "free-shipping"],
)
def test_order_total(lines: list[tuple[int, int]], expected: int) -> None:
    assert order_total(lines) == expected


def test_order_total_currently_charges_shipping_at_exactly_the_threshold() -> None:
    # Pinned, not approved: free shipping needs strictly more than 5000.
    assert order_total([(1000, 5)]) == 5499


def test_order_total_currently_charges_shipping_on_an_empty_order() -> None:
    # Pinned, not approved: an order with no lines still costs 499.
    assert order_total([]) == 499


def test_order_total_member_discount_rounds_down() -> None:
    # 999 - (999 * 5 // 100 = 49) = 950, + 499 shipping
    assert order_total([(999, 1)], member=True) == 1449


def test_order_total_member_discount_stacks_on_bulk() -> None:
    # 1100 - 10% = 990; 990 - (4950 // 100 = 49) = 941; + 499 shipping
    assert order_total([(100, 11)], member=True) == 1440


def test_order_total_coupon_after_member_discount_can_bring_back_shipping() -> None:
    # 10000 - 5% = 9500; HALF = 4750, under the threshold again; + 499 shipping
    assert order_total([(10000, 1)], member=True, coupon="HALF") == 5249


def test_order_total_currently_adds_shipping_to_a_negative_subtotal() -> None:
    # Pinned, not approved: 300 - 500 = -200, then + 499 shipping.
    assert order_total([(300, 1)], coupon="FLAT500") == 299


def test_order_total_appends_one_audit_line_per_call(audit_log: Path) -> None:
    order_total([(1000, 2)], member=True, coupon="HALF")
    order_total([])

    assert audit_log.read_text(encoding="utf-8").splitlines() == [
        "1 lines, member=True, coupon=HALF: 1449",
        "0 lines, member=False, coupon=None: 499",
    ]
