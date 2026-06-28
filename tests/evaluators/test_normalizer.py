"""Tests for the ``Normalizer`` strategy (Track C1).

Covers the 0-1 goodness convention (1 = best, 0 = worst, higher always better):
the :class:`RampNormalizer` in both directions (higher-is-worse + higher-is-better),
its ``good == bad`` guard, plus :class:`PercentNormalizer` and :class:`Identity`.
Every output is asserted to land inside ``[0.0, 1.0]``.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.evaluators.normalizer import (
    Identity,
    Normalizer,
    PercentNormalizer,
    RampNormalizer,
)


def test_ramp_higher_is_worse_cyclomatic_complexity() -> None:
    """``RampNormalizer(good=10, bad=20)``: CC endpoints, midpoint, both clamps."""
    n = RampNormalizer(good=10.0, bad=20.0)
    assert n.normalize(10.0) == 1.0  # raw == good -> best
    assert n.normalize(15.0) == 0.5  # midpoint
    assert n.normalize(20.0) == 0.0  # raw == bad -> worst
    assert n.normalize(25.0) == 0.0  # past bad -> clamped to 0
    assert n.normalize(5.0) == 1.0  # better than good -> clamped to 1


def test_ramp_higher_is_better_coverage() -> None:
    """``RampNormalizer(good=100, bad=0)``: higher-is-better ramp."""
    n = RampNormalizer(good=100.0, bad=0.0)
    assert n.normalize(80.0) == pytest.approx(0.8)
    assert n.normalize(100.0) == 1.0
    assert n.normalize(0.0) == 0.0
    assert n.normalize(150.0) == 1.0  # past good -> clamped to 1
    assert n.normalize(-5.0) == 0.0  # below bad -> clamped to 0


def test_ramp_good_equals_bad_raises() -> None:
    """A degenerate ramp (zero span) is a programming error."""
    with pytest.raises(ValueError):
        RampNormalizer(good=10.0, bad=10.0)


def test_percent_normalizer() -> None:
    """``PercentNormalizer``: 0-100 scaled to 0-1, clamped both ends."""
    n = PercentNormalizer()
    assert n.normalize(80.0) == pytest.approx(0.8)
    assert n.normalize(0.0) == 0.0
    assert n.normalize(100.0) == 1.0
    assert n.normalize(150.0) == 1.0  # clamp high
    assert n.normalize(-5.0) == 0.0  # clamp low


def test_identity_normalizer() -> None:
    """``Identity``: already-0-1 metrics pass through, clamped at the edges."""
    n = Identity()
    assert n.normalize(0.3) == pytest.approx(0.3)
    assert n.normalize(1.5) == 1.0  # clamp high
    assert n.normalize(-0.2) == 0.0  # clamp low


@pytest.mark.parametrize(
    "norm",
    [
        RampNormalizer(good=10.0, bad=20.0),
        RampNormalizer(good=100.0, bad=0.0),
        PercentNormalizer(),
        Identity(),
    ],
)
@pytest.mark.parametrize("raw", [-100.0, -5.0, 0.0, 0.3, 15.0, 80.0, 100.0, 1000.0])
def test_outputs_within_unit_interval(norm: Normalizer, raw: float) -> None:
    """Every normalizer keeps its output inside ``[0.0, 1.0]`` for any raw value."""
    out = norm.normalize(raw)
    assert 0.0 <= out <= 1.0
