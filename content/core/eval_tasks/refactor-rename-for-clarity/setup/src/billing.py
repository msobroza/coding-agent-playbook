"""Compute an invoice total from line items.

The original author wrote this in a hurry — every variable is a single letter
and the formula reads like a textbook exercise rather than business logic.
A rename pass should make the intent obvious without changing the math.
"""

from collections.abc import Iterable


def compute_invoice(
    rows: Iterable[tuple[str, int, float]],
    d: float = 0.0,
    t: float = 0.0,
) -> dict[str, float]:
    """Return ``{"subtotal", "discount", "tax", "total"}`` cents-rounded to two places."""
    s = 0.0
    for _, q, p in rows:
        x = q * p
        s += x
    r = s * (1 - d)
    z = r * t
    o = r + z
    return {
        "subtotal": round(s, 2),
        "discount": round(s - r, 2),
        "tax": round(z, 2),
        "total": round(o, 2),
    }
