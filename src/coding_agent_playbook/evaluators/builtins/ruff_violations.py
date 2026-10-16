"""``ruff_violations``: ruff's count of each configured code family per file (prK §F.2.1).

A thin wrapper over ruff, a consumer-toolchain subprocess (never an engine
import; addendum D-Q1). One call per side per file::

    <ruff> check --no-fix --exit-zero --force-exclude --output-format json
           --stdin-filename <label> --select <every family's codes>
           [--config <key>=<value> ...] [--preview] -

with the source on stdin, run in the repository root. Candidate and baseline
both go through stdin, so the metric needs no worktree and is identical on both
sides; ``--force-exclude`` keeps the project's excludes effective, and
``--select`` (not ``--extend-select``) counts exactly the configured codes while
the project's ``per-file-ignores`` and ``# noqa`` still apply.

Each configured family yields one FILE measurement keyed
``<label>::ruff:<family>``, including a zero, so ``0 -> 1`` is a regression. A
syntax error, a failed or timed-out call, or unreadable output yields **no**
measurement, never a zero. The metric is opt-in (``OPT_IN_METRICS``) and
unavailable without ``tool_paths["ruff"]``.

Its normalizer saturates at 5 (``RampNormalizer(good=0, bad=5)``): a family
already at five or more violations no longer regresses (§21.8 caveat).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evaluators.metric import Metric, register_metric
from coding_agent_playbook.evaluators.normalizer import RampNormalizer
from coding_agent_playbook.evaluators.parse import scope_key
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.tool_runner import ToolRunError, subprocess_tool_runner
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.evaluators.types import EvalContext, RuffSettings

__all__ = [
    "METRIC_NAME",
    "SCOPE_PREFIX",
    "RuffHit",
    "RuffViolationsMetric",
    "count_by_family",
    "parse_ruff_json",
    "ruff_argv",
    "ruff_family",
    "ruff_hits",
]

METRIC_NAME: Final = "ruff_violations"
#: The qualname part of a family's scope key: ``src/x.py::ruff:quality``.
SCOPE_PREFIX: Final = "ruff:"
#: How ruff names a parse failure: ``code: null`` before 0.17, ``invalid-syntax`` since.
_SYNTAX_CODES: Final = frozenset({"invalid-syntax", "syntax-error", "E999"})


@dataclass(frozen=True, slots=True)
class RuffHit:
    """One diagnostic ruff reported: its code, 1-based line and message.

    Example::

        >>> RuffHit("C901", 3, "`parse` is too complex (12 > 10)").code
        'C901'
    """

    code: str
    row: int
    message: str


def ruff_argv(ruff: str, label: str, settings: RuffSettings) -> list[str]:
    """The one ``ruff check`` call for the source labelled ``label`` (fed on stdin).

    Example::

        >>> ruff_argv("ruff", "src/x.py", RuffSettings(families={"quality": ("C901",)}))[-3:]
        ['--select', 'C901', '-']
    """
    argv = [ruff, "check", "--no-fix", "--exit-zero", "--force-exclude", "--output-format"]
    argv += ["json", "--stdin-filename", label]
    for flag in settings.config:
        argv += ["--config", flag]
    if settings.preview:
        argv.append("--preview")
    return [*argv, "--select", ",".join(settings.codes()), "-"]


def parse_ruff_json(stdout: bytes) -> tuple[RuffHit, ...] | None:
    """``--output-format json`` as hits; ``None`` for a syntax error or malformed output.

    Example::

        >>> parse_ruff_json(b'[{"code": "C901", "location": {"row": 2}, "message": "x"}]')
        (RuffHit(code='C901', row=2, message='x'),)
    """
    try:
        rows = json.loads(stdout or b"[]")
    except ValueError:
        return None
    if not isinstance(rows, list):
        return None
    hits = [_hit(row) for row in rows]
    return None if any(hit is None for hit in hits) else tuple(h for h in hits if h is not None)


def _hit(row: object) -> RuffHit | None:
    """One JSON row as a hit; ``None`` when it is a parse error or not a diagnostic."""
    if not isinstance(row, dict):
        return None
    code, location, message = row.get("code"), row.get("location"), row.get("message")
    line = location.get("row") if isinstance(location, dict) else None
    if not isinstance(code, str) or code in _SYNTAX_CODES or type(line) is not int:
        return None
    return RuffHit(code, line, message if isinstance(message, str) else "")


def ruff_hits(ctx: EvalContext) -> tuple[RuffHit, ...] | None:
    """Run ruff over ``ctx.source`` as ``ctx.label``; ``None`` when it gave no usable answer.

    Goes through ``ctx.tool_setup.runner`` (a memo inside the gate), so asking
    again for the same text costs no second process.

    Example::

        >>> ruff_hits(EvalContext(module=None, source="x = 1\\n", label="a.py"))
        None
    """
    ruff = ctx.tool_paths.get("ruff")
    setup = ctx.tool_setup
    if not ruff or not setup.ruff.codes():
        return None  # no ruff, or every family emptied: ruff would reject an empty --select
    runner = setup.runner if setup.runner is not None else subprocess_tool_runner
    argv = ruff_argv(ruff, ctx.label, setup.ruff)
    try:
        returncode, stdout = runner(argv, ctx.source.encode("utf-8"), setup.cwd, setup.timeout_s)
    except ToolRunError:
        return None
    return parse_ruff_json(stdout) if returncode == 0 else None


def count_by_family(
    hits: Iterable[RuffHit], families: Mapping[str, Sequence[str]]
) -> dict[str, int]:
    """How many ``hits`` each family's codes select (prefix-aware); other codes count nowhere.

    Example::

        >>> count_by_family([RuffHit("D103", 1, "")], {"docstrings": ["D1"], "quality": ["C901"]})
        {'docstrings': 1, 'quality': 0}
    """
    found = list(hits)
    return {
        family: sum(1 for hit in found if any(hit.code.startswith(code) for code in codes))
        for family, codes in families.items()
    }


def ruff_family(key: str) -> str | None:
    """The family of a ``ruff_violations`` scope key, else ``None``.

    Example::

        >>> ruff_family("src/x.py::ruff:docstrings"), ruff_family("src/x.py::parse")
        ('docstrings', None)
    """
    _, _, qualname = key.partition("::")
    return qualname[len(SCOPE_PREFIX) :] if qualname.startswith(SCOPE_PREFIX) else None


def _measure(ctx: EvalContext) -> list[Measurement]:
    """One measurement per configured family; none when ruff gave no usable answer."""
    if ctx.module is None:
        return []
    hits = ruff_hits(ctx)
    if hits is None:
        return []
    counts = count_by_family(hits, ctx.tool_setup.ruff.families)
    return [
        Measurement(METRIC_NAME, scope_key(ctx.label, f"{SCOPE_PREFIX}{family}"), float(count))
        for family, count in counts.items()
    ]


@register_metric
class RuffViolationsMetric(Metric):
    """``ruff_violations`` as a :class:`Metric`: per-family ruff counts over a whole file."""

    name = METRIC_NAME
    scope = Scope.FILE
    normalizer = RampNormalizer(good=0, bad=5)

    def available(self, ctx: EvalContext) -> bool:
        """Only with a parsed module and a ruff to run (``tool_paths["ruff"]``)."""
        return ctx.module is not None and bool(ctx.tool_paths.get("ruff"))

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
