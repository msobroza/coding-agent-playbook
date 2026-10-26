"""Token usage sums and the price that turns tokens into cost (``evals.token_usage``, ticket 07)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.evals.token_usage import TokenPrice, TokenUsage, sum_usage


def test_usage_adds_up_and_totals() -> None:
    total = TokenUsage(10, 2) + TokenUsage(5, 1)
    assert (total, total.total) == (TokenUsage(15, 3), 18)


def test_sum_is_unknown_when_any_run_reported_no_usage() -> None:
    assert sum_usage([TokenUsage(1, 1), TokenUsage(2, 3)]) == TokenUsage(3, 4)
    assert sum_usage([TokenUsage(1, 1), None]) is None
    assert sum_usage([]) is None


def test_price_is_per_million_input_and_output_tokens() -> None:
    price = TokenPrice(input_per_million=3.0, output_per_million=15.0)
    assert price.cost_usd(TokenUsage(2_000_000, 100_000)) == pytest.approx(7.5)
