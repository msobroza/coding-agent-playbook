"""``cognitive_complexity``: complexipy's cognitive complexity per function (SonarSource's metric).

A thin wrapper over complexipy (8.2 or later), a consumer-toolchain subprocess
like ``ruff_violations`` (never an engine import; addendum D-Q1). complexipy
reads no stdin, so each side's source is written to ``measured.py`` in a fresh
temporary directory, and one call measures it there::

    <complexipy> measured.py --plain --ignore-complexity --isolated -C no

``--isolated`` ignores any ``[tool.complexipy]`` table (``failed`` or ``top``
there would cut the listing), the cache complexipy writes stays in the
temporary directory, and the consumer's ``# noqa: complexipy`` comments still
apply. Each call has its own path, so the gate's memo never answers it: an
unchanged file costs two calls.

Each listed function yields one FUNCTION measurement keyed by its qualname
(complexipy's ``Box::method`` is ``parse_module``'s ``Box.method``); a nested
function counts toward the function around it, and defs that share a qualname
keep the highest value. A syntax error, a failed or timed-out call, or a
complexipy too old for these flags yields **no** measurement, never a zero. The
metric is opt-in (``OPT_IN_METRICS``) and unavailable without
``tool_paths["complexipy"]``.

The default limit is the standard one, 15 per function: SonarSource's rule
S3776 and complexipy's own ``max-complexity-allowed``. The score is 1.0 up to
15 and drops 0.01 per point above it (``RampNormalizer(good=15, bad=115)``), so
the default ``fail = 1.0`` fails a new function over 15, and growth only
regresses above 15. It saturates at 115 (§21.8 caveat).
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.grading.metric import Metric, register_metric
from coding_agent_playbook.grading.normalizer import RampNormalizer
from coding_agent_playbook.grading.parse import scope_key
from coding_agent_playbook.grading.scope import Scope
from coding_agent_playbook.grading.tool_runner import ToolRunError, subprocess_tool_runner
from coding_agent_playbook.grading.types import Measurement

if TYPE_CHECKING:
    from coding_agent_playbook.grading.types import EvalContext

__all__ = [
    "MEASURED_FILE",
    "METRIC_NAME",
    "TOOL",
    "CognitiveComplexityMetric",
    "complexipy_argv",
    "complexipy_scores",
    "parse_complexipy_plain",
]

METRIC_NAME: Final = "cognitive_complexity"
#: The ``tool_paths`` key: the CLI finds it on ``PATH``, a hook through its ``machine.json`` pin.
TOOL: Final = "complexipy"
#: The file each side's source is written to, inside a fresh temporary directory.
MEASURED_FILE: Final = "measured.py"
#: One ``--plain`` row: ``measured.py <qualname> <complexity>``; complexipy's notes never match.
_ROW: Final = re.compile(rf"^{re.escape(MEASURED_FILE)} (\S+) (\d+)$")


def complexipy_argv(complexipy: str) -> list[str]:
    """The one complexipy call over :data:`MEASURED_FILE`, run in its directory.

    Example::

        >>> complexipy_argv("complexipy")[:3]
        ['complexipy', 'measured.py', '--plain']
    """
    return [complexipy, MEASURED_FILE, "--plain", "--ignore-complexity", "--isolated", "-C", "no"]


def parse_complexipy_plain(stdout: bytes) -> dict[str, int]:
    """``--plain`` output as ``{qualname: complexity}``; a shared qualname keeps its highest value.

    Example::

        >>> parse_complexipy_plain(b"measured.py Box::run 4\\nmeasured.py load 0\\n")
        {'Box.run': 4, 'load': 0}
    """
    scores: dict[str, int] = {}
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        row = _ROW.match(line.strip())
        if row is None:
            continue
        qualname = row.group(1).replace("::", ".")
        scores[qualname] = max(int(row.group(2)), scores.get(qualname, 0))
    return scores


def complexipy_scores(ctx: EvalContext) -> dict[str, int] | None:
    """Run complexipy over ``ctx.source``; ``None`` when it gave no usable answer.

    Goes through ``ctx.tool_setup.runner`` (a hook's runner over its pin).

    Example::

        >>> complexipy_scores(EvalContext(module=None, source="x = 1\\n", label="a.py"))
        None
    """
    complexipy = ctx.tool_paths.get(TOOL)
    if not complexipy:
        return None
    setup = ctx.tool_setup
    runner = setup.runner if setup.runner is not None else subprocess_tool_runner
    with tempfile.TemporaryDirectory(prefix="playbook-cognitive-") as scratch:
        workdir = Path(scratch)
        (workdir / MEASURED_FILE).write_text(ctx.source, encoding="utf-8")
        try:
            returncode, stdout = runner(complexipy_argv(complexipy), b"", workdir, setup.timeout_s)
        except ToolRunError:
            return None
    return parse_complexipy_plain(stdout) if returncode == 0 else None


def _measure(ctx: EvalContext) -> list[Measurement]:
    """One measurement per function complexipy lists; none when it gave no usable answer."""
    if ctx.module is None:
        return []
    scores = complexipy_scores(ctx)
    if scores is None:
        return []
    return [
        Measurement(METRIC_NAME, scope_key(ctx.label, qualname), float(value))
        for qualname, value in scores.items()
    ]


@register_metric
class CognitiveComplexityMetric(Metric):
    """``cognitive_complexity`` as a :class:`Metric`: 1.0 up to 15 per function, 0.0 at 115."""

    name = METRIC_NAME
    scope = Scope.FUNCTION
    normalizer = RampNormalizer(good=15, bad=115)
    tool = TOOL

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        return _measure(ctx)
