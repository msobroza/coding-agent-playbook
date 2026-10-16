"""Shared helpers for the Stop-stage hook tests (specs/prK-hook-pack.md §E.2, §E.0.7).

Every Stop is a real ``playbook-hook simulate stop`` dispatch with a golden
Claude payload relocated into a :class:`PackRepo`; ``FakeGit`` answers the
fingerprint and the git reads, ``FakeStageRunner`` stands in for ruff, mypy
and pytest, and the session ledger is seeded as ``post_tool_use`` writes it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.git import Fingerprint
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME, session_key
from coding_agent_playbook.hook_runtime.stop.runner import ToolRun
from tests.hook_payloads import load_hook_payload
from tests.hook_runtime.fakes import FakeGit, FakeStageRunner, FakeTrustStore

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import ProcPort, RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_runtime.fakes import StageCall
    from tests.hooks.pack_repo import PackRepo

TREE: Final = "1a2b3c4d" * 5
HEAD_TREE: Final = "f" * 40
CLAIM: Final = "All done: tests pass."
NO_CLAIM: Final = "Refactored the parser; next I will look at the cache."


def changed_git(tree: str = TREE, **fields: Any) -> FakeGit:
    """A ``FakeGit`` whose working tree differs from ``HEAD`` (fingerprint ``tree``)."""
    fingerprint = Fingerprint(tree_id=tree, aux="", mode="tree", unchanged_vs_head=False)
    fields.setdefault("head_tree_id", HEAD_TREE)
    return FakeGit(fingerprint_value=fingerprint, **fields)


def stop_payload(repo: PackRepo, *, message: str = CLAIM, case: str = "plain") -> bytes:
    """The golden Claude Stop payload in ``repo``, its last assistant message replaced."""
    body = json.loads(repo.relocate(load_hook_payload("claude_code", "stop", case)))
    body["last_assistant_message"] = message
    return json.dumps(body).encode("utf-8")


def session_of(payload: bytes) -> str:
    return str(json.loads(payload)["session_id"])


def seed_ledger(state: Path, session_id: str, *lines: Mapping[str, Any]) -> None:
    """Append ``lines`` to the session ledger, as ``post_tool_use`` dispatches would."""
    ledger = state / STATE_DIR_NAME / "sessions" / session_key(session_id) / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps({"v": 1, "ev": "post_tool_use", **line}) + "\n")


def py_edit(*paths: str, cats: Iterable[str] = ("py",)) -> dict[str, Any]:
    """A ledger line for an Edit of ``paths``."""
    return {"tc": "edit", "tool": "Edit", "paths": list(paths), "cats": sorted(cats)}


def ruff_row(path: str, code: str, message: str, row: int) -> dict[str, Any]:
    """One ``ruff check --output-format=json`` row."""
    return {"filename": path, "code": code, "message": message, "location": {"row": row}}


def script_ruff(
    runner: FakeStageRunner,
    *,
    worktree: Iterable[Mapping[str, Any]] = (),
    baseline: Iterable[Mapping[str, Any]] = (),
    unformatted: Iterable[str] = (),
    baseline_unformatted: Iterable[str] = (),
    spy: Callable[[StageCall], None] | None = None,
) -> None:
    """Answer ruff per call: the worktree (``cwd`` ``None``) or the ``HEAD`` export."""
    check = {False: list(worktree), True: list(baseline)}
    fmt = {False: list(unformatted), True: list(baseline_unformatted)}

    def answer(call: StageCall) -> ToolRun:
        if spy is not None:
            spy(call)
        export = call.cwd is not None
        if call.args[:1] == ("format",):
            files = fmt[export]
            out = "".join(f"Would reformat: {f}\n" for f in files).encode()
            return ToolRun("ruff", 1 if files else 0, out)
        rows = check[export]
        return ToolRun("ruff", 1 if rows else 0, json.dumps(rows).encode())

    runner.answer("ruff", answer)


def stop(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    payload: bytes,
    *,
    git: FakeGit,
    state: Path,
    runner: FakeStageRunner | None = None,
    trust: FakeTrustStore | None = None,
    proc: ProcPort | None = None,
) -> SimulateReport:
    """One Stop dispatch with the given fakes (a clean ruff when ``runner`` is omitted).

    ``proc`` replaces the spawn-refusing ``FakeProc``: ``FakeRuff`` for the
    metrics pass's pinned ruff.
    """
    if runner is None:
        runner = FakeStageRunner()
        script_ruff(runner)
    fields: dict[str, Any] = {
        "git": git,
        "stage_runner": runner,
        "trust": trust or FakeTrustStore(),
    }
    if proc is not None:
        fields["proc"] = proc
    return repo.simulate(payload, deps(**fields), event=EventName.STOP, state=state)


def reason_lines(report: SimulateReport) -> list[str]:
    return report.trace.combined.reason.splitlines()
