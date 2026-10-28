"""quotient without the zero-numerator branch, which the tests showed was redundant."""


def quotient(numerator: int, denominator: int) -> float:
    """Divide ``numerator`` by ``denominator``."""
    if not isinstance(numerator, int) or not isinstance(denominator, int):
        raise TypeError("quotient requires integer arguments")
    if denominator == 0:
        raise ZeroDivisionError("denominator must be non-zero")
    return numerator / denominator
