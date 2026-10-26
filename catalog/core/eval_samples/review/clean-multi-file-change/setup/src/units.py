"""Weight conversions for the shipping quotes."""

#: Kilograms in one of each supported unit; the pound is exact by definition.
KILOGRAMS_PER_UNIT: dict[str, float] = {"kg": 1.0, "lb": 0.45359237}


def to_kilograms(weight: float, unit: str) -> float:
    """``weight`` given in ``unit``, as kilograms; an unknown unit raises ``ValueError``."""
    try:
        factor = KILOGRAMS_PER_UNIT[unit]
    except KeyError:
        raise ValueError(
            f"unknown weight unit {unit!r}; expected one of {sorted(KILOGRAMS_PER_UNIT)}"
        ) from None
    return weight * factor
