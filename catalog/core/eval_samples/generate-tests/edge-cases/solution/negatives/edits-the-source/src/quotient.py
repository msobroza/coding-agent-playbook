"""A function with several branches; the eval expects each branch to be tested."""


def quotient(numerator: int, denominator: int) -> float:
    """Divide ``numerator`` by ``denominator``.

    Raises ``ZeroDivisionError`` when ``denominator`` is zero and ``TypeError``
    when either argument is not an ``int``.
    """
    if not isinstance(numerator, int) or not isinstance(denominator, int):
        raise TypeError("quotient requires integer arguments")
    if denominator == 0:
        raise ZeroDivisionError("denominator must be non-zero")
    return numerator / denominator
