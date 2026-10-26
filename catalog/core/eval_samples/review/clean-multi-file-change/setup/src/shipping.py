"""Shipping quotes: a flat base fee plus a rate per started kilogram."""

import math

from src.units import to_kilograms

BASE_FEE_CENTS = 450
CENTS_PER_KILOGRAM = 120


def quote_cents(weight: float, unit: str = "kg") -> int:
    """Price in cents to ship ``weight`` in ``unit``; every started kilogram is charged."""
    if weight <= 0:
        raise ValueError(f"weight must be positive, got {weight}")
    return BASE_FEE_CENTS + CENTS_PER_KILOGRAM * math.ceil(to_kilograms(weight, unit))
