"""Token counts of an agent run and the price that turns them into a cost (spec #281 ticket 07).

A harness that reports its token usage fills a :class:`TokenUsage`; release
metrics average it per sample. Cost comes only from an Eval target's declared
:class:`TokenPrice` (USD per million input and output tokens): the harness's own
estimate is never used, because for a custom endpoint it prices an unknown model
from a bundled table and means nothing.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from functools import reduce
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Prices are declared per million tokens.
_TOKENS_PER_PRICE_UNIT: Final = 1_000_000


@dataclass(frozen=True)
class TokenUsage:
    """Input and output tokens of one agent run (or a sum of runs).

    ``input_tokens`` counts every prompt token, cache reads and writes included,
    so a price per input token applies to all of them.

    Example::

        >>> (TokenUsage(10, 2) + TokenUsage(5, 1)).total
        18
    """

    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        """Input plus output tokens.

        Example::

            >>> TokenUsage(3, 4).total
            7
        """
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass(frozen=True)
class TokenPrice:
    """An Eval target's ``price``: USD per million input and per million output tokens.

    Example::

        >>> TokenPrice(3.0, 15.0).cost_usd(TokenUsage(1_000_000, 100_000))
        4.5
    """

    input_per_million: float
    output_per_million: float

    def cost_usd(self, usage: TokenUsage) -> float:
        """The cost of ``usage`` at this price, in USD.

        Example::

            >>> TokenPrice(0.0, 0.0).cost_usd(TokenUsage(5, 5))
            0.0
        """
        input_cost = usage.input_tokens * self.input_per_million
        output_cost = usage.output_tokens * self.output_per_million
        return (input_cost + output_cost) / _TOKENS_PER_PRICE_UNIT


def sum_usage(usages: Sequence[TokenUsage | None]) -> TokenUsage | None:
    """The sum of ``usages``, or ``None`` when any is unknown (or there are none).

    A partial sum would undercount, so one run without usage makes the total unknown.

    Example::

        >>> sum_usage([TokenUsage(1, 1), TokenUsage(2, 2)])
        TokenUsage(input_tokens=3, output_tokens=3)
        >>> sum_usage([TokenUsage(1, 1), None]) is None
        True
    """
    known = [usage for usage in usages if usage is not None]
    if not usages or len(known) != len(usages):
        return None
    return reduce(operator.add, known)
