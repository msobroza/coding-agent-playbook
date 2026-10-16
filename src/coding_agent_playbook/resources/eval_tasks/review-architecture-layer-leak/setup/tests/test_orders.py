from pathlib import Path

import pytest
from shop.models import LineItem
from shop.orders import order_total, place_order


def test_place_order_persists_the_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # place_order always opens ./orders.db, so the test has to move the process.
    monkeypatch.chdir(tmp_path)
    order = place_order("c-1", [LineItem(sku="A1", quantity=2, unit_price_cents=150)])
    assert order_total(order) == 300
    assert (tmp_path / "orders.db").exists()


def test_place_order_rejects_an_empty_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        place_order("c-1", [])
