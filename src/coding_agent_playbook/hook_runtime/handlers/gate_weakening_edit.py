"""gate-weakening-guard's ``pre_edit`` companion: ask before a test is skipped or deleted (specs/prK-hook-pack.md §E.2).

``pre_tool_use``, handler ``gate_weakening_guard:pre_edit``. It acts on two
things only, and asks (unattended and on OpenCode the ask becomes a deny
through K2's ask degradation):

- an Edit/Write of a test file (the ``test`` path class: ``tests/``,
  ``test_*.py``, ``*_test.py``, ``conftest.py``) that **adds** an unjustified
  ``@pytest.mark.skip``, ``skipif(True)``, non-strict ``xfail`` or
  ``pytest.skip(``, judged by ``gate_scan``'s own patterns on the lines the
  edit adds (the simulated file after the edit, against the file now);
- a Bash ``rm``, ``git rm`` or ``mv`` of a test file.

Any other call returns at once, before ``gate_scan`` is imported.
"""

from __future__ import annotations

import posixpath
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.handlers._targets import (
    file_write_paths,
    shell_write_targets,
)
from coding_agent_playbook.hook_runtime.registry import register_hook_handler

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.globs import GlobSet
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = ["SKIP_RULES", "gate_weakening_pre_edit"]

#: The ``gate_scan`` rules that skip or soften a test.
SKIP_RULES: Final = frozenset(
    {"pytest-skip-marker", "pytest-skipif-true", "pytest-xfail-non-strict", "pytest-skip-call"}
)
_TEST_CLASS: Final = "test"
_READ_LIMIT: Final = 1024 * 1024
_PATH_CHARS: Final = 80
_SKIP_REASON: Final = (
    "A skipped or non-strict xfail test hides a failure instead of fixing it. Fix the code or "
    "the test; if it must be skipped, say why to the user."
)
_DELETE_REASON: Final = (
    "Deleting a test file removes the checks it makes. Fix the code under test instead, or "
    "explain to the user why the test should go."
)


@register_hook_handler(
    "gate_weakening_guard:pre_edit", events=["pre_tool_use"], decisions=["deny", "ask", "none"]
)
def gate_weakening_pre_edit(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Ask before an edit adds a skip/xfail marker to a test, or a command deletes a test file.

    Example::

        >>> gate_weakening_pre_edit(edit_adding_skip_marker, ctx).decision  # doctest: +SKIP
        <Decision.ASK: 'ask'>
    """
    tests = ctx.cfg.path_classes.get(_TEST_CLASS)
    if ev.tool is None or ev.repo is None or tests is None:
        return None
    for path in shell_write_targets(ev, ctx, _deleted_operands):
        if _is_test(path, tests):
            return _ask(ctx, "test_deleted", f"{_quoted(path)} is a test file.\n{_DELETE_REASON}")
    for path in file_write_paths(ev.tool):
        rule = _added_skip(ev.tool, path) if _is_test(path, tests) else None
        if rule is not None:
            return _ask(ctx, rule, f"{_quoted(path)}: the edit adds {rule}.\n{_SKIP_REASON}")
    return None


def _deleted_operands(segment: Segment) -> list[str]:
    """The paths ``rm``, ``git rm`` or ``mv`` (its sources) removes."""
    from coding_agent_playbook.hook_runtime.shell.writes import operands

    argv = list(segment.argv)
    program = posixpath.basename(argv[0]) if argv else ""
    if program == "rm":
        return operands(argv[1:])
    if program == "git" and argv[1:2] == ["rm"]:
        return operands(argv[2:])
    if program == "mv":
        return operands(argv[1:])[:-1]
    return []


def _is_test(path: NormalizedPath, tests: GlobSet) -> bool:
    return path.repo_rel is not None and (tests.matches(path.key) or tests.matches(f"{path.key}/"))


def _added_skip(tool: ToolCall, path: NormalizedPath) -> str | None:
    """The first skip rule an unjustified added line of ``path`` matches, else ``None``."""
    from coding_agent_playbook.gate_scan import (
        DEFAULT_ADDED_LINE_PATTERNS,
        AddedLine,
        ScanPolicy,
        scan,
    )

    rel = path.repo_rel or ""
    policy = replace(
        ScanPolicy(source_roots=()),
        patterns=tuple(p for p in DEFAULT_ADDED_LINE_PATTERNS if p.rule in SKIP_RULES),
    )
    added = [AddedLine(rel, 0, text) for text in _added_texts(tool, path)]
    blocking = scan(added, (), (), policy).blocking
    return blocking[0].rule if blocking else None


def _added_texts(tool: ToolCall, path: NormalizedPath) -> list[str]:
    """The lines the call adds to ``path``: simulated after-text minus the current text."""
    from coding_agent_playbook.hook_runtime.edit_preview import preview_after

    before = _read(path)
    after = preview_after(tool, before)
    if after is None:  # a call that cannot be simulated: judge everything it writes
        return [
            line
            for fragment in tool.content
            if fragment.path == path.raw
            for line in fragment.text.splitlines()
        ]
    kept = Counter((before or "").splitlines())
    added: list[str] = []
    for line in after.splitlines():
        if kept[line] > 0:
            kept[line] -= 1
        else:
            added.append(line)
    return added


def _read(path: NormalizedPath) -> str | None:
    from coding_agent_playbook.hook_runtime.config.reader import read_small_file

    if not path.exists:
        return None
    try:
        data, _ = read_small_file(Path(path.realpath), _READ_LIMIT)
        return data.decode("utf-8")
    except (OSError, ValueError):  # unreadable, too large, not UTF-8: judge the whole edit
        return None


def _quoted(path: NormalizedPath) -> str:
    return quote_data(path.repo_rel or path.raw, _PATH_CHARS)


def _ask(ctx: HandlerContext, rule_id: str, reason: str) -> HandlerResult:
    return HandlerResult(decision=Decision.ASK, hook_id=ctx.hook.id, rule_id=rule_id, reason=reason)
