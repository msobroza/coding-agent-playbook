"""The ``Normalizer`` strategy: a metric's raw value -> 0-1 "goodness".

Every metric measures on its own native scale - cyclomatic complexity is an
unbounded ``int`` where larger is *worse*, coverage runs ``0-100`` where larger
is *better*, ``test_pass_rate`` is already ``0-1``. A :class:`Normalizer` is the
Strategy that erases those differences: it maps one raw measurement to a ``0-1``
**goodness** where, by convention, ``1.0`` is the best possible outcome and
``0.0`` the worst, and **higher is always better** regardless of the metric's
native direction. Folding direction into the normalizer is what let the grading
layer drop the per-metric direction flag: a metric just owns the normalizer that
already points the right way.

The primitives are deliberately tiny and direction-agnostic:

* :class:`RampNormalizer` - a linear ramp between a ``good`` anchor (-> ``1.0``)
  and a ``bad`` anchor (-> ``0.0``). Because ``good`` and ``bad`` are arbitrary
  values, the *same* formula handles both directions: ``good=10, bad=20`` ramps a
  higher-is-worse metric down, ``good=100, bad=0`` ramps a higher-is-better one
  up.
* :class:`PercentNormalizer` - the ``0-100 -> 0-1`` special case (coverage,
  ``maintainability_index``); equivalent to ``RampNormalizer(100, 0)`` but named
  for clarity.
* :class:`Identity` - a pass-through (with clamp) for metrics already on ``0-1``
  (``test_pass_rate``, judged scores).

All outputs are clamped to ``[0.0, 1.0]`` via :func:`_clamp01`, so a raw value
outside the anchors saturates rather than overshooting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


def _clamp01(x: float) -> float:
    """Clamp ``x`` into the closed unit interval ``[0.0, 1.0]``."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


class Normalizer(ABC):
    """Strategy mapping a metric's raw value to a ``0-1`` goodness (higher = better).

    Subclasses implement :meth:`normalize`, which must return a value clamped to
    ``[0.0, 1.0]`` where ``1.0`` is the best outcome and ``0.0`` the worst. The
    metric's native direction (larger-is-worse vs larger-is-better) is baked into
    the concrete normalizer, so callers never reason about direction themselves.
    """

    @abstractmethod
    def normalize(self, raw: float) -> float:
        """Map ``raw`` to a ``0-1`` goodness, clamped to ``[0.0, 1.0]``."""


@dataclass(frozen=True)
class RampNormalizer(Normalizer):
    """A linear ramp between a ``good`` anchor (-> ``1.0``) and a ``bad`` one (-> ``0.0``).

    ``raw == good`` scores ``1.0``, ``raw == bad`` scores ``0.0``, values between
    interpolate linearly, and values outside the anchors saturate (clamped). The
    single formula ``_clamp01((raw - bad) / (good - bad))`` is **direction-free**:
    swapping which anchor is larger flips the slope, so the same class serves both
    a higher-is-worse metric (``good=10, bad=20``: CC ``15 -> 0.5``) and a
    higher-is-better one (``good=100, bad=0``: coverage ``80 -> 0.8``).
    """

    good: float
    bad: float

    def __post_init__(self) -> None:
        if self.good == self.bad:
            raise ValueError(
                f"RampNormalizer needs distinct anchors; got good == bad == {self.good!r}"
            )

    def normalize(self, raw: float) -> float:
        return _clamp01((raw - self.bad) / (self.good - self.bad))


@dataclass(frozen=True)
class PercentNormalizer(Normalizer):
    """The ``0-100 -> 0-1`` ramp for percentage metrics (coverage, ``maintainability_index``).

    ``normalize(raw) = _clamp01(raw / 100.0)``. Equivalent to
    ``RampNormalizer(good=100, bad=0)`` but named for the common percentage case.
    """

    def normalize(self, raw: float) -> float:
        return _clamp01(raw / 100.0)


@dataclass(frozen=True)
class Identity(Normalizer):
    """A pass-through (with clamp) for metrics already on a ``0-1`` goodness scale.

    ``normalize(raw) = _clamp01(raw)`` - for ``test_pass_rate`` and judged scores,
    which already report ``0-1`` where higher is better.
    """

    def normalize(self, raw: float) -> float:
        return _clamp01(raw)


__all__ = [
    "Identity",
    "Normalizer",
    "PercentNormalizer",
    "RampNormalizer",
]
