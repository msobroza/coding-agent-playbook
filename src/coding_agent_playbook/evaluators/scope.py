"""Evaluator enums: ``Scope``, ``ValueKind``, ``Determinism`` (SPEC prM §A).

These three axes describe *what* an evaluator measures over, *what kind* of
value it yields, and *who* produces it. They are kept in a dependency-free leaf
module so every other evaluator module can import them without cycles.
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


class ValueKind(Enum):
    """The raw value's units.

    ``SCORE`` is already a normalized ``0-1`` value and ``BOOL`` is ``0|1``;
    both default to identity normalization in ``Evaluator.to_score``. ``NUMERIC``
    is an arbitrary metric (e.g. cyclomatic complexity) that gets ramped.
    """

    NUMERIC = "numeric"
    SCORE = "score"
    BOOL = "bool"


class Determinism(Enum):
    """Who produces the value, which drives regression semantics + routing.

    ``DETERMINISTIC`` evaluators (static metrics, execution metrics) compare
    exactly (``max_worsening=0``); ``JUDGED`` evaluators (LLM/human rubric) use a
    tolerance band and only run once a ``Judge`` is configured (v1.1).
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
