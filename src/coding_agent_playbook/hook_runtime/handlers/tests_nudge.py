"""tests-with-source-nudge: the ``tests-nudge`` Stop stage (specs/prK-hook-pack.md §E.2).

For each changed ``.py`` file under the source roots it compares the ``ast``
of the working tree with ``HEAD:<path>`` and collects the **new** public
symbols (:func:`new_public_symbols`). A symbol whose name has no whole-word
match under the test roots (``git grep -w``) gets one line:

``New public API without tests: "src/x.py"::foo``

- Changed (as opposed to new) symbols are never reported.
- It is silent when the last message ends with ``?``: the agent is asking, not done.
- At most :data:`MAX_FILES` files are parsed per Stop.
- It is context by default; ``[hooks.tests-with-source-nudge] block = true``
  makes the lines a deny, inside the coordinator's budget.
- The coordinator runs it only when no stage up to ``verify-claim`` is red.
- The roots are baked into its config at sync (``_guard_config_verify``),
  never read at run time. It fails open: an unparseable file is skipped.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._public_api import new_public_symbols
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.paths import fold_key
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.stop.alone import run_alone
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort
    from coding_agent_playbook.hook_runtime.stop.stages import StopPlan

__all__ = [
    "CONFIG_SCHEMA",
    "MAX_FILES",
    "STAGE_NAME",
    "NudgeStage",
    "tests_nudge_stage",
    "tests_with_source_nudge",
]

STAGE_NAME: Final = "tests-nudge"
#: Files parsed per Stop (two ``ast.parse`` each: the tree and ``HEAD``).
MAX_FILES: Final = 20
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
    "block": ConfigKey("boolean"),
    "source_roots": ConfigKey("list"),
    "test_roots": ConfigKey("list"),
}
_MAX_SOURCE_BYTES: Final = 512 * 1024
#: Path classes that are never "source": tests themselves and frozen eval fixtures.
_NOT_SOURCE: Final = ("test", "eval_fixture")


@dataclass(frozen=True, slots=True, kw_only=True)
class NudgeStage:
    """The ``tests-nudge`` stage of one Stop; ``is_excluded`` drops tests, fixtures and secrets.

    Example::

        >>> tests_nudge_stage(stop_event, ctx).run(plan, deadline).lines  # doctest: +SKIP
        ('New public API without tests: "src/x.py"::public_fn',)
    """

    git: GitPort
    root: str
    source_roots: tuple[str, ...]
    test_roots: tuple[str, ...]
    is_excluded: Callable[[str], bool]
    question: bool = False
    block: bool = False
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = True
    mode: str = "warn"

    def applies(self, plan: StopPlan) -> bool:
        """Skipped when the agent's last message asks a question."""
        return not self.question

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """One line per new public symbol no test mentions; warn, or red under ``block``."""
        if plan.head_tree is None:  # an unborn branch: nothing is "new" against it
            return StageResult(STAGE_NAME, "green")
        lines = [
            f"New public API without tests: {quote_data(rel)}::{symbol}"
            for rel in self._changed()[:MAX_FILES]
            for symbol in self._new_symbols(rel)
            if not self.git.grep_word(symbol.rpartition(".")[2], self.test_roots)
        ]
        if not lines:
            return StageResult(STAGE_NAME, "green")
        return StageResult(STAGE_NAME, "red" if self.block else "warn", lines=tuple(lines))

    def _changed(self) -> list[str]:
        """Changed and untracked ``.py`` files under the source roots, tests excluded."""
        found = dict.fromkeys(self.git.diff_worktree("HEAD").paths)
        found.update(dict.fromkeys(self.git.ls_untracked()))
        return [
            rel
            for rel in found
            if rel.endswith(".py") and _under(rel, self.source_roots) and not self._excluded(rel)
        ]

    def _excluded(self, rel: str) -> bool:
        return self.is_excluded(rel) or _under(rel, self.test_roots)

    def _new_symbols(self, rel: str) -> list[str]:
        after = _read_source(self.root, rel)
        if after is None:
            return []
        before = self.git.cat_head(rel)
        old = None if before is None else before.decode("utf-8", errors="replace")
        return new_public_symbols(old, after)


def tests_nudge_stage(ev: CanonicalEvent, ctx: HandlerContext) -> NudgeStage | None:
    """The ``tests-nudge`` stage for ``ev``'s repository: the coordinator's factory.

    Example: ``tests_nudge_stage(stop_event, ctx).source_roots == ("src",)``.
    """
    if ev.repo is None:
        return None
    message = ev.stop.last_assistant_message if ev.stop is not None else ""
    platform, cfg = ctx.platform, ctx.cfg
    config = HookConfig(ctx.config, CONFIG_SCHEMA)
    # Each root is a repo-relative prefix; "." (or a bare "/") is the repository root.
    sources = config.strings("source_roots", blanks="drop_empty")
    tests = config.strings("test_roots", blanks="drop_empty")
    classes = [cfg.path_classes[name] for name in _NOT_SOURCE if name in cfg.path_classes]

    def excluded(rel: str) -> bool:
        key = fold_key(rel, platform)
        return cfg.secret_paths.matches(key) or any(globs.matches(key) for globs in classes)

    return NudgeStage(
        git=ctx.git,
        root=ev.repo.worktree_root,
        source_roots=tuple(root.strip("/") or "." for root in sources) or (".",),
        test_roots=tuple(root.strip("/") or "." for root in tests) or ("tests",),
        is_excluded=excluded,
        question=message.rstrip().endswith("?"),
        block=config.flag("block", False),
    )


@register_hook_handler(
    "tests_with_source_nudge",
    events=["stop"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
)
def tests_with_source_nudge(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Run the ``tests-nudge`` stage alone (no coordinator selected).

    Example: ``tests_with_source_nudge(stop_after_new_public_fn, ctx)``.
    """
    stage = tests_nudge_stage(ev, ctx)
    return None if stage is None else run_alone(stage, ev, ctx)


def _under(rel: str, roots: Sequence[str]) -> bool:
    return any(root == "." or rel == root or rel.startswith(f"{root}/") for root in roots)


def _read_source(root: str, rel: str) -> str | None:
    """A small UTF-8 source file of the worktree; ``None`` when absent, large or binary."""
    try:
        with open(os.path.join(root, rel), "rb") as handle:
            data = handle.read(_MAX_SOURCE_BYTES + 1)
    except OSError:
        return None
    if len(data) > _MAX_SOURCE_BYTES or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None
