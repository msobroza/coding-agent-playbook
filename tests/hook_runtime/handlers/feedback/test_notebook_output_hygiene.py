"""notebook-output-hygiene: agent-edited notebooks that keep outputs (specs/prK-hook-pack.md §E.3).

A fixture repository with a notebook (``has_notebooks``; the hook is opt-in)
drives NotebookEdit and Write ``post_tool_use`` payloads through
``playbook-hook simulate``, then a Stop through the coordinator, whose
``notebooks`` stage rescans the diff's ``.ipynb`` files. ``FakeGit`` answers
the ``HEAD`` notebook and the working-tree diff.
"""

from __future__ import annotations

import base64
import dataclasses
import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.git.safe_git import AddedLine, Fingerprint
from coding_agent_playbook.hook_runtime.handlers.notebooks import NotebooksStage
from coding_agent_playbook.hooks.guard_config.inputs import DetectInputs
from tests.hook_runtime.fakes import FakeGit
from tests.hook_runtime.handlers.pack_repo import engine_hook, resolve_engine_hooks

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from tests.hook_runtime.handlers.pack_repo import PackRepo

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "notebook-output-hygiene"
COORDINATOR: Final = "stop-ci-parity-gate"
NB: Final = "nb/explore.ipynb"
NOTEBOOKS: Final = DetectInputs(facts={"has_notebooks": True})
ADVICE: Final = "Outputs may embed data rows; strip outputs before committing."
#: A 2 MB PNG, base64-encoded as Jupyter stores it.
PNG: Final = base64.b64encode(b"\x89PNG\r\n" + b"\x00" * 1_500_000).decode("ascii")


def _cell(cell_id: str, source: str, outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": cell_id, "cell_type": "code", "source": source, "outputs": outputs or []}


def _notebook(*cells: dict[str, Any]) -> str:
    return json.dumps({"cells": list(cells), "metadata": {}, "nbformat": 4, "nbformat_minor": 5})


IMAGE: Final = {"output_type": "display_data", "data": {"image/png": PNG}, "metadata": {}}
TEXT: Final = {"output_type": "stream", "name": "stdout", "text": ["3\n"]}


def _install(repo: PackRepo, hooks: tuple[str, ...] = (HOOK_ID,), **kw: Any) -> None:
    repo.install_pack(list(hooks), detect=NOTEBOOKS, **kw)


def _notebook_edit(
    repo: PackRepo,
    deps: RuntimeDeps,
    *,
    cell_id: str = "c1",
    mode: str = "replace",
    state: Path | None = None,
) -> SimulateReport:
    tool_input = {
        "notebook_path": str(repo.root / NB),
        "cell_id": cell_id,
        "new_source": "plot(df)",
        "edit_mode": mode,
    }
    payload = repo.tool_payload("NotebookEdit", tool_input, event=EventName.POST_TOOL_USE)
    return repo.simulate(payload, deps, event=EventName.POST_TOOL_USE, state=state)


def _write(repo: PackRepo, deps: RuntimeDeps, text: str) -> SimulateReport:
    repo.write(NB, text)  # post_tool_use: the tool already wrote it
    tool_input = {"file_path": str(repo.root / NB), "content": text}
    payload = repo.tool_payload("Write", tool_input, event=EventName.POST_TOOL_USE)
    return repo.simulate(payload, deps, event=EventName.POST_TOOL_USE)


def test_2mb_base64_png_output_warns(pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    pack_repo.write(NB, _notebook(_cell("c0", "import pandas"), _cell("c1", "plot(df)", [IMAGE])))
    _install(pack_repo)

    report = _notebook_edit(pack_repo, deps(git=FakeGit()))

    assert report.trace.combined.decision is Decision.CONTEXT
    assert report.trace.combined.context == (
        f'"{NB}": cell c1 keeps outputs (an image/base64 payload; over 64 KB of output). {ADVICE}',
    )


def test_stripped_notebook_silent(pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    pack_repo.write(NB, _notebook(_cell("c1", "plot(df)")))
    _install(pack_repo)

    report = _notebook_edit(pack_repo, deps(git=FakeGit()))

    assert report.trace.combined.decision is Decision.NONE


def test_only_touched_cells_are_checked(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    legacy = _cell("c0", "x = 1", [TEXT])
    head = _notebook(legacy, _cell("c1", "y = 2"))
    _install(pack_repo)
    git = FakeGit(head_blobs={NB: head.encode()})

    quiet = _write(pack_repo, deps(git=git), _notebook(legacy, _cell("c1", "y = 3")))
    loud = _write(pack_repo, deps(git=git), _notebook(legacy, _cell("c1", "y = 3", [TEXT])))

    assert quiet.trace.combined.decision is Decision.NONE  # c0's output predates the session
    assert loud.trace.combined.context == (f'"{NB}": cell c1 keeps outputs. {ADVICE}',)


def test_oversized_file_warns_without_json_load(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], monkeypatch: pytest.MonkeyPatch
) -> None:
    pack_repo.write(NB, _notebook(_cell("c1", "plot(df)", [IMAGE])))
    _install(pack_repo, extra_tables={"notebooks": {"max_bytes": 1024 * 1024}})
    parsed: list[str] = []
    real_load = json.load

    def spy(handle: Any, **kw: Any) -> Any:
        parsed.append(str(getattr(handle, "name", "")))
        return real_load(handle, **kw)

    monkeypatch.setattr(json, "load", spy)

    report = _notebook_edit(pack_repo, deps(git=FakeGit()))

    assert [name for name in parsed if name.endswith(".ipynb")] == []
    assert report.trace.combined.context == (
        f'"{NB}" is over 1 MiB and was not parsed: it likely keeps outputs. {ADVICE}',
    )


def test_once_per_notebook_per_session(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    pack_repo.write(NB, _notebook(_cell("c1", "plot(df)", [TEXT])))
    _install(pack_repo)
    state = tmp_path / "state"

    first = _notebook_edit(pack_repo, deps(git=FakeGit()), state=state)
    second = _notebook_edit(pack_repo, deps(git=FakeGit()), state=state)

    assert first.trace.combined.decision is Decision.CONTEXT
    assert second.trace.combined.decision is Decision.NONE


def test_deleted_cell_checks_nothing(pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    pack_repo.write(NB, _notebook(_cell("c1", "plot(df)", [TEXT])))
    _install(pack_repo)

    report = _notebook_edit(pack_repo, deps(git=FakeGit()), mode="delete")

    assert report.trace.combined.decision is Decision.NONE


def test_repo_without_notebooks_not_rendered(tmp_path: Path) -> None:
    assert resolve_engine_hooks([HOOK_ID], tmp_path, facts={}) == []
    [hook] = resolve_engine_hooks([HOOK_ID], tmp_path, facts={"has_notebooks": True})
    assert hook.handlers["stop"].config == {"stage": "notebooks", "mode": "warn"}


def _stop(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, git: FakeGit
) -> SimulateReport:
    payload = repo.payload(EventName.STOP, stop_hook_active=False)
    return repo.simulate(payload, deps(git=git), event=EventName.STOP, state=state)


def _diff_git() -> FakeGit:
    fingerprint = Fingerprint(tree_id="1a2b3c4d" * 5, aux="", mode="tree", unchanged_vs_head=False)
    return FakeGit(
        fingerprint_value=fingerprint,
        head_tree_id="f" * 40,
        added=(AddedLine(NB, 3, '"outputs": ['), AddedLine("src/app.py", 1, "x = 1")),
    )


@pytest.mark.parametrize(
    "hooks", [(COORDINATOR, HOOK_ID), (HOOK_ID,)], ids=["coordinator", "alone"]
)
def test_stop_stage_adds_one_line_for_diff_ipynb(
    pack_repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    tmp_path: Path,
    hooks: tuple[str, ...],
) -> None:
    pack_repo.write(NB, _notebook(_cell("c1", "plot(df)", [IMAGE])))
    _install(pack_repo, hooks)
    state = tmp_path / "state"
    _notebook_edit(pack_repo, deps(git=FakeGit()), state=state)  # the ledger records the write

    report = _stop(pack_repo, deps, state, _diff_git())

    assert report.trace.combined.decision is Decision.NONE  # warn only: never a block
    assert f'[notebooks] Notebooks keep outputs: "{NB}". {ADVICE}' in (
        report.trace.combined.user_notes
    )


def test_stop_stage_inactive_without_a_notebook_write(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    pack_repo.write(NB, _notebook(_cell("c1", "plot(df)", [IMAGE])))
    _install(pack_repo, (COORDINATOR, HOOK_ID))
    git = _diff_git()

    report = _stop(pack_repo, deps, tmp_path / "state", git)

    # The coordinator's own stages (K6's lint, verify-claim) may add their notes; this one adds none.
    notes = report.trace.combined.user_notes
    assert not [note for note in notes if note.startswith("[notebooks]")]
    assert ("diff_added", ()) not in git.calls


def test_shipped_hook_matches_its_pack_row(pack_repo: PackRepo) -> None:
    fm = engine_hook(HOOK_ID).frontmatter
    _install(pack_repo, (COORDINATOR, HOOK_ID))
    rendered = json.loads(
        pack_repo.root.joinpath(".coding-agent-playbook/hooks/guard_config.json").read_bytes()
    )
    defaults = {
        f.name: f.default
        for f in dataclasses.fields(NotebooksStage)
        if f.name in ("needs_diff", "mode")
    }

    assert (fm.tier, tuple(fm.events), fm.on_error, fm.applies_if) == (
        "opt-in",
        ("post_tool_use", "stop"),
        "open",
        {"has_notebooks": True},
    )
    [record] = [r for r in rendered["stop_gate"]["stages"] if r["name"] == "notebooks"]
    assert (record["owner"], record["cost"], record["mode"]) == (HOOK_ID, "deterministic", "warn")
    assert record["needs_diff"] is True
    assert rendered["notebooks"] == {"max_bytes": 5 * 1024 * 1024}
    assert defaults == {"needs_diff": True, "mode": "warn"}
