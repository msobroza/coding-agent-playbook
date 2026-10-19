"""guard-eval-fixtures: protect frozen eval ``setup/`` fixtures from agent "fixes" (specs/prK-hook-pack.md §E.1).

Opt-in, ``pre_tool_use``. A target is a fixture when it matches
``guard_config.eval.fixture_globs`` (default ``**/eval_tasks/*/setup/**``):
the file tool's write paths, every Bash write target (``sed -i``, redirects,
``cp`` destinations) and the path operands of a formatter (``ruff format``,
``ruff [check] --fix``, ``black``, ``isort``). It passes when:

- the task is being authored: its ``task.toml`` is absent at ``HEAD``
  (``SafeGit.cat_head``), or the session ledger shows this session wrote it;
- the user already approved: the ledger shows an earlier successful write
  under the same task's ``setup/`` (an ask the user answered yes).

Otherwise it asks: ``setup/`` is the frozen starting state, find-injected-vuln
fixtures are intentionally vulnerable and ``file_unchanged`` gates compare
against it. Unattended (``claude -p``, the eval runners) and on OpenCode the
ask becomes a deny through K2's ask degradation. Deliberately not guard-class
(``on_error: open``): the primary fix is the ruff ``extend-exclude`` +
``force-exclude`` (P9) and a validate fixture-integrity check.
"""

from __future__ import annotations

import posixpath
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.artifacts.path_classes import FIXTURE_GLOBS, task_path
from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.registry import register_hook_handler
from coding_agent_playbook.hook_runtime.globs import compile_globs
from coding_agent_playbook.hook_runtime.handlers._targets import (
    file_write_paths,
    shell_write_targets,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.artifacts.path_classes import TaskPath
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.globs import GlobSet
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = ["FROZEN_REASON", "guard_eval_fixtures"]

FROZEN_REASON: Final = (
    "setup/ is the frozen starting state; find-injected-vuln fixtures are intentionally "
    "vulnerable and file_unchanged gates compare against it."
)
#: Ledger tool classes whose ``writes`` are file changes the user let through.
_WRITE_CLASSES: Final = frozenset({"edit", "write", "notebook_edit", "shell"})
_FORMATTERS: Final = frozenset({"black", "isort"})
_PATH_CHARS: Final = 60


@register_hook_handler("guard_eval_fixtures", events=["pre_tool_use"], decisions=["ask", "none"])
def guard_eval_fixtures(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Ask before a write into a committed eval task's ``setup/``; ``None`` (pass) otherwise.

    Example::

        >>> guard_eval_fixtures(edit_of_frozen_loader, ctx).reason.splitlines()[1]
        ... # doctest: +SKIP
        'setup/ is the frozen starting state; ...'
    """
    if ev.tool is None or ev.repo is None:
        return None
    globs = _fixture_globs(ctx)
    hits = [w for p in _targets(ev, ctx) if (w := _fixture(p, globs)) is not None]
    if not hits:
        return None
    records = ctx.ledger.read() if ctx.ledger is not None else []
    for where in hits:
        if not (_authoring(ctx, where, records) or _approved(where, records)):
            return _ask(ctx, where)
    return None


def _targets(ev: CanonicalEvent, ctx: HandlerContext) -> list[NormalizedPath]:
    """File-tool write paths, then each Bash segment's write targets and formatter operands."""
    from coding_agent_playbook.hook_runtime.shell.parse import write_targets  # Bash branch only

    assert ev.tool is not None  # checked by the handler
    found = file_write_paths(ev.tool)

    def extract(segment: Segment) -> list[str]:
        return [*write_targets(segment), *_formatter_paths(segment.argv)]

    found.extend(shell_write_targets(ev, ctx, extract))
    return found


def _formatter_paths(argv: Sequence[str]) -> list[str]:
    """The path operands of ``ruff format``, ``ruff [check] --fix``, ``black`` or ``isort``."""
    from coding_agent_playbook.hook_runtime.shell.writes import operands

    if not argv:
        return []
    program, args = posixpath.basename(argv[0]), list(argv[1:])
    if program in _FORMATTERS:
        return operands(args)
    if program != "ruff":
        return []
    if args[:1] == ["format"]:
        return operands(args[1:])
    if "--fix" in args:
        return operands(args[1:] if args[:1] == ["check"] else args)
    return []


def _fixture_globs(ctx: HandlerContext) -> GlobSet:
    globs = ctx.cfg.tables.eval_fixture_globs(FIXTURE_GLOBS)
    return compile_globs(globs, platform=ctx.platform)


def _fixture(path: NormalizedPath, globs: GlobSet) -> TaskPath | None:
    """The task whose ``setup/`` holds ``path`` (or is ``path``), else ``None``."""
    if path.repo_rel is None or not (globs.matches(path.key) or globs.matches(f"{path.key}/")):
        return None
    where = task_path(path.repo_rel)
    return where if where is not None and where.in_setup else None


def _authoring(ctx: HandlerContext, where: TaskPath, records: Sequence[Mapping[str, Any]]) -> bool:
    """The task's ``task.toml`` is not at ``HEAD``, or this session wrote it."""
    toml = f"{where.task_dir}/task.toml"
    return ctx.git.cat_head(toml) is None or any(toml in _writes(r) for r in records)


def _approved(where: TaskPath, records: Sequence[Mapping[str, Any]]) -> bool:
    """An earlier successful write under the same ``setup/`` this session (the user said yes)."""
    prefix = f"{where.task_dir}/setup/"
    return any(
        record.get("ev") == "post_tool_use" and any(w.startswith(prefix) for w in _writes(record))
        for record in records
    )


def _writes(record: Mapping[str, Any]) -> list[str]:
    if record.get("tc") not in _WRITE_CLASSES:
        return []
    writes = record.get("writes", [])
    return [w for w in writes if isinstance(w, str)] if isinstance(writes, list) else []


def _ask(ctx: HandlerContext, where: TaskPath) -> HandlerResult:
    """The ask: the path within its task (so the line fits the 160-character cap), then why."""
    head = (
        f"{quote_data(where.rest, _PATH_CHARS)} is a frozen fixture of eval task "
        f"{quote_data(where.task_id, _PATH_CHARS)}."
    )
    return HandlerResult(
        decision=Decision.ASK,
        hook_id=ctx.hook.id,
        rule_id="frozen_fixture",
        reason=f"{head}\n{FROZEN_REASON}",
    )
