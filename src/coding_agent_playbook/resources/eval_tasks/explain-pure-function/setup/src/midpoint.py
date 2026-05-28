"""Compute the integer midpoint of two non-negative integers.

The implementation uses the bit-arithmetic formulation that avoids the
overflow trap of ``(a + b) // 2`` in fixed-width contexts. Python ints are
arbitrary-precision so the bug never manifests here, but the technique is
worth keeping for code that may be ported.
"""


def midpoint(a: int, b: int) -> int:
    """Return the integer midpoint of ``a`` and ``b``.

    Equivalent to ``(a + b) // 2`` for non-negative inputs, but written via
    addition of the AND and the XOR halved — a formulation that is
    overflow-safe in fixed-width arithmetic.
    """
    if a < 0 or b < 0:
        raise ValueError("midpoint requires non-negative integers")
    return (a & b) + ((a ^ b) >> 1)
