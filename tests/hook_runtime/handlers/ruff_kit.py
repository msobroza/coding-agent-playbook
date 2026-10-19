"""Drivers shared by the §E.3 ruff-consumer hook tests (specs/prK-hook-pack.md §E.3).

The pinned ruff is ``FakeRuff`` behind ``RuntimeDeps.proc``; ``machine.json``
names a stub file (the ``ruff_program`` fixture), so the pin's stat signature
is real. ``FakeGit`` answers the HEAD blob. Every edit runs the full
``playbook-hook simulate post_tool_use`` pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.config.pin import write_machine_pins
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hooks.guard_config.ruff_probe import (
    probe_ruff_rules,
    ruff_candidate_codes,
    ruff_drop_codes,
)
from tests.hook_runtime.fakes import FakeGit, FakeRuff

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook
    from tests.hook_runtime.handlers.pack_repo import PackRepo

__all__ = ["context", "edit", "head_git", "pin_ruff", "probed_drops", "value_of"]


def pin_ruff(
    repo: PackRepo, program: Path, *, drops: Mapping[str, Sequence[str]] | None = None
) -> None:
    """Pin ``program`` as this worktree's ruff, as a write-mode sync would."""
    git_dir = str(repo.root / ".git")
    write_machine_pins(
        tools={"ruff": [str(program)]}, engine_version="0.1.0a0", drops=drops, git_dir=git_dir
    )


def probed_drops(
    program: Path, hooks: Sequence[ResolvedHook], rules: Sequence[dict[str, object]]
) -> dict[str, list[str]]:
    """The ``tools.ruff.drop`` sync computes: the hooks' codes the ruff (``rules``) cannot run."""
    codes = ruff_candidate_codes(hooks)
    probe = probe_ruff_rules([str(program)], codes, proc=FakeRuff(rules=list(rules)))
    drop = ruff_drop_codes(codes, probe)
    return {"ruff": drop} if drop else {}


def head_git(head: str | None, rel: str) -> FakeGit:
    """``FakeGit`` with ``rel`` at HEAD as ``head`` (``None``: a new, untracked file)."""
    return FakeGit(head_blobs={} if head is None else {rel: head.encode()})


def edit(
    repo: PackRepo, deps: RuntimeDeps, rel: str, *, state: Path | None = None, **fields: Any
) -> SimulateReport:
    """A Claude ``Edit`` of ``rel`` (repo-relative or absolute) through ``simulate post_tool_use``.

    ``fields`` override payload keys (``session_id="s-2"``: another session).
    """
    path = rel if rel.startswith("/") else str(repo.root / rel)
    tool_input = {"file_path": path, "old_string": "a", "new_string": "b"}
    payload = repo.tool_payload("Edit", tool_input, event=EventName.POST_TOOL_USE, **fields)
    return repo.simulate(payload, deps, event=EventName.POST_TOOL_USE, state=state)


def context(report: SimulateReport) -> list[str]:
    """The combined ``context`` lines the model sees."""
    return list(report.trace.combined.context)


def value_of(args: tuple[str, ...], flag: str) -> str:
    """The argument after ``flag`` in a recorded ruff argv."""
    return args[args.index(flag) + 1]
