"""gate-weakening-guard: the ``gate-integrity`` Stop stage (specs/prK-hook-pack.md §E.2).

It applies ``judges.gate_weakening.scan``, the one policy its CI twin ``playbook gate-scan``
also applies, to the working tree's change from ``HEAD``: the added and
removed lines of ``git diff HEAD -U0`` plus every line of untracked text files,
and the protected config files before and after. Secret paths are never read.

- Unjustified findings (a bare ``# type: ignore``, a new skip marker, a
  loosened ``--cov-fail-under``) join the coordinator's one combined block,
  which already fires once per fingerprint: ``Fix the root cause or justify
  each inline``.
- Loosened config and new escape pragmas **always** reach the user as a
  note too, even when justified (once per session per finding).

The policy is the engine default extended by the hook's merged config
(``added_line_patterns`` and ``protected_config_keys`` extend,
``justification_regex`` replaces): the shipped ``HOOK.md`` adds nothing, so
the hook and the CLI twin share ``judges.gate_weakening``'s defaults as their one source.
``judges.gate_weakening`` is imported only when the stage runs. The ``pre_edit``
companion lives in :mod:`.gate_weakening_edit`.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.paths import fold_key
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.stop.alone import run_alone
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.judges.gate_weakening import (
        AddedLine,
        Finding,
        ScanPolicy,
        ScanReport,
    )
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.stop.stages import StopPlan

__all__ = [
    "CONFIG_SCHEMA",
    "FIX_HINT",
    "POLICY_KEYS",
    "STAGE_NAME",
    "GateIntegrityStage",
    "gate_integrity_stage",
    "gate_weakening_guard",
    "scan_policy",
]

STAGE_NAME: Final = "gate-integrity"
#: The ``[hooks.gate-weakening-guard]`` keys ``judges.gate_weakening.policy_from_table`` reads.
POLICY_KEYS: Final = ("added_line_patterns", "protected_config_keys", "justification_regex")
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
    "added_line_patterns": ConfigKey("list", "extend"),
    "protected_config_keys": ConfigKey("list", "extend"),
    "justification_regex": ConfigKey("string"),
}
FIX_HINT: Final = "Fix the root cause or justify each inline with a trailing `# <reason>`."
_MAX_UNTRACKED_FILES: Final = 200
_MAX_UNTRACKED_BYTES: Final = 256 * 1024
_DETAIL_CHARS: Final = 100
_NOTE_LABEL: Final = {"loosening": "Gate loosened", "pragma": "Escape pragma added"}


def scan_policy(config: Mapping[str, Any], root: str) -> ScanPolicy:
    """``judges.gate_weakening``'s default policy extended by the hook's merged ``config``.

    Source roots are ``src`` when the worktree has one, else the root (as the CLI twin).
    Raises ``ValueError`` naming a malformed key.

    Example: ``scan_policy({}, "/repo") == ScanPolicy(source_roots=("src",))`` with ``src/``.
    """
    from coding_agent_playbook.hook_runtime.judges.gate_weakening import (
        ScanPolicy,
        policy_from_table,
    )

    roots = ("src",) if os.path.isdir(os.path.join(root, "src")) else ("",)
    table = {key: config[key] for key in POLICY_KEYS if key in config}
    return policy_from_table(table, ScanPolicy(source_roots=roots))


@dataclass(frozen=True, slots=True, kw_only=True)
class GateIntegrityStage:
    """The ``gate-integrity`` stage of one Stop.

    Example::

        >>> gate_integrity_stage(stop_event, ctx).run(plan, deadline).lines[-1]  # doctest: +SKIP
        'Fix the root cause or justify each inline with a trailing `# <reason>`.'
    """

    ctx: HandlerContext
    root: str
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = True
    mode: str = "block"

    def applies(self, plan: StopPlan) -> bool:
        """Every changed tree is scanned (the coordinator skips unchanged ones)."""
        return True

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """Red on unjustified findings; loosenings and pragmas always as user notes."""
        if plan.head_tree is None:  # an unborn branch has nothing to weaken
            return StageResult(STAGE_NAME, "green")
        report = self._scan()
        notes = tuple(_note(f) for f in report.notes if self._first(f))
        if not report.blocking:
            return StageResult(STAGE_NAME, "green", user_lines=notes)
        lines = (*(_block_line(f) for f in report.blocking), FIX_HINT)
        return StageResult(STAGE_NAME, "red", lines=lines, user_lines=notes)

    def _scan(self) -> ScanReport:
        from coding_agent_playbook.hook_runtime.judges.gate_weakening import (
            ConfigPair,
            is_config_path,
            scan,
        )

        git, secret = self.ctx.git, self._secret
        diff = git.diff_worktree("HEAD")
        untracked = [rel for rel in git.ls_untracked() if not secret(rel)]
        added = [line for line in diff.added if not secret(line.path)]
        added += _untracked_lines(self.root, untracked[:_MAX_UNTRACKED_FILES])
        removed = [line for line in diff.removed if not secret(line.path)]
        pairs = [
            ConfigPair(path, _decoded(git.cat_head(path)), _read_text(self.root, path))
            for path in dict.fromkeys([*diff.paths, *untracked])
            if is_config_path(path) and not secret(path)
        ]
        return scan(added, removed, pairs, scan_policy(self.ctx.config, self.root))

    def _secret(self, rel: str) -> bool:
        return self.ctx.cfg.secret_paths.matches(fold_key(rel, self.ctx.platform))

    def _first(self, finding: Finding) -> bool:
        digest = hashlib.sha256(finding.line_text().encode("utf-8")).hexdigest()[:16]
        return self.ctx.session.once(f"gate-integrity:note:{digest}")


def gate_integrity_stage(ev: CanonicalEvent, ctx: HandlerContext) -> GateIntegrityStage | None:
    """The ``gate-integrity`` stage for ``ev``'s repository: the coordinator's factory.

    Example: ``gate_integrity_stage(stop_event, ctx).name == "gate-integrity"``.
    """
    return None if ev.repo is None else GateIntegrityStage(ctx=ctx, root=ev.repo.worktree_root)


@register_hook_handler(
    "gate_weakening_guard",
    events=["stop"],
    decisions=["deny", "ask", "none"],  # the hook's set: its companion asks (H5)
    config_schema=CONFIG_SCHEMA,
)
def gate_weakening_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Run the ``gate-integrity`` stage alone (no coordinator selected).

    Example: ``gate_weakening_guard(stop_after_bare_type_ignore, ctx).decision``.
    """
    stage = gate_integrity_stage(ev, ctx)
    return None if stage is None else run_alone(stage, ev, ctx)


def _untracked_lines(root: str, rels: list[str]) -> list[AddedLine]:
    """Every line of each untracked UTF-8 text file (a new file is all added lines)."""
    from coding_agent_playbook.hook_runtime.judges.gate_weakening import AddedLine

    lines: list[AddedLine] = []
    for rel in rels:
        text = _read_text(root, rel)
        if text is not None:
            lines.extend(AddedLine(rel, n, t) for n, t in enumerate(text.splitlines(), 1))
    return lines


def _read_text(root: str, rel: str) -> str | None:
    """A small UTF-8 text file of the worktree, ``None`` when absent, large or binary."""
    try:
        with open(os.path.join(root, rel), "rb") as handle:
            data = handle.read(_MAX_UNTRACKED_BYTES + 1)
    except OSError:
        return None
    if len(data) > _MAX_UNTRACKED_BYTES or b"\x00" in data:
        return None
    return _decoded(data)


def _decoded(data: bytes | None) -> str | None:
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _block_line(finding: Finding) -> str:
    where = (
        f"{quote_data(finding.path)}:{finding.line}" if finding.line else quote_data(finding.path)
    )
    return f"{where} {finding.rule}: {quote_data(finding.detail, _DETAIL_CHARS)}"


def _note(finding: Finding) -> str:
    """The user's line: the detail is already one sanitized, clipped line (``judges.gate_weakening``)."""
    label = _NOTE_LABEL.get(finding.kind, "Gate weakened")
    justified = " (justified)" if finding.justified else ""
    where = (
        f"{quote_data(finding.path)}:{finding.line}" if finding.line else quote_data(finding.path)
    )
    return f"{label}{justified}: {where} {finding.rule}: {finding.detail}"
