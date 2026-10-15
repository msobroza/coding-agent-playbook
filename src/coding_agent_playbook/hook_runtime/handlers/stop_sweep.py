"""stop-diff-sweep: the ``secrets`` Stop stage (specs/prK-hook-pack.md §E.4).

Default; detective (state-based): it sees what ``sed -i``, heredocs, scripts
and generators wrote, which no command matcher sees. Planned by the Stop
coordinator after ``gate-integrity`` (``STOP_STAGE_ORDER``), only when the
working tree differs from ``HEAD`` (the coordinator skips settled trees).

- The walk is ``_secret_sweep``: secret tokens on added lines and in
  untracked text files, untracked credential files by path (never read), and
  untracked model/data artifacts or large files as warnings.
- ml-unsafe-deserialization-guard's Bash rescan rides the same walk: when that
  hook is on, every changed ``.py`` file gains a warning line per new block
  sink that no committed ``trusted-artifact`` comment vouches for (an Edit or
  Write would have been denied before reaching the disk; this one was not).
- ``mode`` (``block``, ``warn`` or ``off``, the strictest of every layer,
  ``[guardrails.stop_sweep]`` included): ``block`` joins the coordinator's one
  combined reason per fingerprint; ``warn`` only reports; ``off`` plans nothing.
  A capped sweep tells the user it was partial.
- ``pii`` (empty in the engine; an overlay lists ``security.pii`` detectors,
  ``extend``) adds the PII tier, pii-prompt-guard's file twin (specs/prK-hook-pack.md
  §E.5): PII written into the tree joins the same block as a ``pii:<detector>`` line.

Lines are masked: rule, place and length, never a secret's characters.
``on_error: open``; a failure reads ``NOT verified``, never green.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.handlers._pii_settings import (
    PII_CONFIG_KEY,
    PII_KEY,
    pii_settings,
)
from coding_agent_playbook.hook_runtime.handlers._secret_sweep import (
    SweepLimits,
    SweepReport,
    sweep_tree,
)
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.stop.alone import run_alone
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.handlers.deser import SinkTable
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.stop.stages import StopPlan

__all__ = [
    "CONFIG_SCHEMA",
    "MODES",
    "PARTIAL_NOTE",
    "STAGE_NAME",
    "SecretsStage",
    "secrets_stage",
    "stop_secret_sweep",
]

STAGE_NAME: Final = "secrets"
#: Weakest first: the order ``strictest`` merges by.
MODES: Final = ("off", "warn", "block")
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
    "mode": ConfigKey("string", "strictest", MODES),
    "max_scan_bytes": ConfigKey("integer"),
    "large_file_mb": ConfigKey("integer"),
    "extra_patterns": ConfigKey("regex", "extend"),
    PII_KEY: PII_CONFIG_KEY,
}
PARTIAL_NOTE: Final = (
    "[secrets] partially scanned: the byte cap was reached; run playbook scan-secrets --worktree"
)
DESER_HOOK: Final = "ml-unsafe-deserialization-guard"
#: Finding lines shown before the rest are summarized (the Stop reason is capped at 40).
_LISTED: Final = 12
_DESER_SUFFIX: Final = ".py"
_DESER_ADVICE: Final = "load a data-only format instead"


@dataclass(frozen=True, slots=True, kw_only=True)
class SecretsStage:
    """The ``secrets`` stage of one Stop.

    Example::

        >>> secrets_stage(stop_event, ctx).run(plan, deadline).status  # doctest: +SKIP
        'red'
    """

    ctx: HandlerContext
    root: str
    mode: str = "block"
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = True

    def applies(self, plan: StopPlan) -> bool:
        """Every changed tree is swept (the coordinator skips settled ones)."""
        return True

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """Red on a token or credential file (``block``); warn lines otherwise."""
        del plan, deadline  # git and the working tree are read directly; the walk is bounded
        config = self.ctx.config
        report = sweep_tree(self.ctx, self.root, _limits(config), pii=pii_settings(config))
        report.warnings.extend(_deser_lines(self.ctx, self.root, report.changed))
        return _result(report, self.mode)


def secrets_stage(ev: CanonicalEvent, ctx: HandlerContext) -> SecretsStage | None:
    """The ``secrets`` stage for ``ev``'s repository: the coordinator's factory.

    ``None`` outside a repository and in ``mode = "off"``.
    Example: ``secrets_stage(stop_event, ctx).name == "secrets"``.
    """
    mode = ctx.config.get("mode")
    mode = mode if mode in MODES else "block"
    if ev.repo is None or mode == "off":
        return None
    return SecretsStage(ctx=ctx, root=ev.repo.worktree_root, mode=mode)


@register_hook_handler(
    "stop_secret_sweep",
    events=["stop"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
    config_domain="stop_sweep",
)
def stop_secret_sweep(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Run the ``secrets`` stage alone (no coordinator selected).

    Example: ``stop_secret_sweep(stop_after_sed_wrote_a_key, ctx).decision``.
    """
    stage = secrets_stage(ev, ctx)
    return None if stage is None else run_alone(stage, ev, ctx)


def _result(report: SweepReport, mode: str) -> StageResult:
    notes = (PARTIAL_NOTE,) if report.partial else ()
    lines = (*_listed(report.blocking), *report.warnings)
    if not lines:
        return StageResult(STAGE_NAME, "green", user_lines=notes)
    if report.blocking and mode == "block":
        return StageResult(STAGE_NAME, "red", lines=lines, user_lines=notes)
    return StageResult(STAGE_NAME, "warn", lines=lines, user_lines=notes)


def _listed(lines: list[str]) -> list[str]:
    if len(lines) <= _LISTED:
        return lines
    return [*lines[: _LISTED - 1], f"… and {len(lines) - _LISTED + 1} more secret findings"]


def _limits(config: Mapping[str, object]) -> SweepLimits:
    default = SweepLimits()
    return SweepLimits(
        max_scan_bytes=_positive(config.get("max_scan_bytes"), default.max_scan_bytes),
        large_file_mb=_positive(config.get("large_file_mb"), default.large_file_mb),
    )


def _positive(value: object, default: int) -> int:
    return value if type(value) is int and value > 0 else default


# --- the deserialization rescan (§E.3's Bash backstop) --------------------------------------------


def _deser_lines(ctx: HandlerContext, root: str, changed: list[str]) -> list[str]:
    """One warning per new, unvouched block sink in a changed ``.py`` file (deser hook on)."""
    record = ctx.cfg.hooks.get(DESER_HOOK)
    spec = None if record is None else record.handlers.get(EventName.PRE_TOOL_USE)
    files = [rel for rel in changed if rel.endswith(_DESER_SUFFIX)]
    if spec is None or not files:
        return []
    # Imported only now: the sink visitor (``ast``) is needed only for a changed .py file.
    from coding_agent_playbook.hook_runtime.handlers.deser import SinkTable

    table = SinkTable.from_config(spec.config)
    return [line for rel in files for line in _file_sinks(ctx, root, rel, table)]


def _file_sinks(ctx: HandlerContext, root: str, rel: str, table: SinkTable) -> list[str]:
    from coding_agent_playbook.hook_runtime.escape import pragma_at_head
    from coding_agent_playbook.hook_runtime.handlers.deser import (
        new_sink_calls,
        trusted_artifact_line,
    )

    post = _text(os.path.join(root, rel))
    if post is None:
        return []
    head = ctx.git.cat_head(rel)
    pre = None if head is None else head.decode("utf-8", errors="replace")
    lines: list[str] = []
    for hit in new_sink_calls(pre, post, table):
        pragma = trusted_artifact_line(post, hit.line)
        if hit.kind != "block" or (pragma is not None and pragma_at_head(ctx.git, rel, pragma)):
            continue
        advice = (hit.row.advice or _DESER_ADVICE).rstrip(".")
        lines.append(
            f"{quote_data(rel)}:{hit.line} adds {hit.callee}(...) outside the file tools; {advice}"
        )
    return lines


def _text(path: str) -> str | None:
    try:
        with open(path, "rb") as handle:
            return handle.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    except OSError:
        return None
