"""Metric/Check enums: ``Scope``, ``Determinism``, ``CostTier`` (SPEC prM §A).

These axes describe *what* a metric measures over, *who* produces a check's
value, and *how expensive* a check is to run. They are kept in a dependency-free
leaf module so every other evaluator module can import them without cycles.
"""

from __future__ import annotations

from enum import Enum, IntEnum


class Scope(Enum):
    """The unit a measurement applies to.

    ``MODULE`` means the whole target/suite (e.g. a test-pass-rate over an
    entire run), distinct from ``FILE`` which is a single source file.
    """

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    FILE = "file"
    MODULE = "module"


class Determinism(Enum):
    """Who produces the value, which drives regression semantics + routing.

    ``DETERMINISTIC`` checks (static metrics, execution metrics) compare exactly
    (``max_worsening=0``); ``JUDGED`` checks (LLM/human rubric) use a tolerance
    band and only run once a ``Judge`` is configured (v1.1).
    """

    DETERMINISTIC = "deterministic"
    JUDGED = "judged"


class CostTier(IntEnum):
    """How expensive a check is to run, ordered cheapest-first (T1).

    The :class:`Metric`/:class:`Check`/:class:`Rubric` scheduler sorts checks by
    this tier so the cheapest deterministic checks run before opt-in execution
    checks, and judged checks (which need a ``Judge``) run last. Backed by
    :class:`enum.IntEnum` so ``DETERMINISTIC < EXECUTION < JUDGED`` compares
    directly and the members sort in tier order.
    """

    DETERMINISTIC = 0
    EXECUTION = 1
    JUDGED = 2
