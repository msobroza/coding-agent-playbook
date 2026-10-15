"""eval-task-authoring-lint: parse and trial-compile an edited eval task (specs/prK-hook-pack.md §E.1).

Each case writes a repo-local eval task (``playbook/eval_tasks/<id>/``) and its
prompt, then dispatches ``post_tool_use`` through ``playbook-hook simulate``.
The parse and compile run in-process (``evals.loader`` / ``evals.validator``,
jinja2-free); the one ``playbook eval --show`` echo is a child process that
``FakeProc`` scripts. ``playbook eval --run`` (real runners, the LLM judge)
must never be reached: the runner and judge entry-point groups are spied.
"""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from tests.hook_runtime.fakes import FakeClock, FakeProc
from tests.hooks.pack_repo import PackRepo, playbook_calls, playbook_child

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase

    type Payload = Callable[[str, str, str], HookPayloadCase]

HOOK_ID: Final = "eval-task-authoring-lint"
TASK_DIR: Final = "playbook/eval_tasks/demo-task"
TASK: Final = f"{TASK_DIR}/task.toml"
HINT: Final = "author regex patterns as TOML literal strings (single quotes)"
_PROMPT: Final = (
    "---\nid: demo\nname: Demo\ndescription: Demo prompt.\nslash: demo\n"
    "eval_tasks:\n  - demo-task\n---\nReview the code.\n"
)
VALID: Final = """\
id = "demo-task"
prompt_id = "demo"
description = "Demo."
version = 1

[setup]
files = ["src/app.py"]
project_kind = "python-application"

[invocation]
prompt_args = "review src/app.py"
input_variables = {}

[gate]
expr = "untouched"

[gate.bind]
untouched = { check = "file_unchanged", path = "src/app.py" }

[verdict]
trial = "gate"
"""
BAD_ESCAPE: Final = VALID.replace(
    '[gate]\nexpr = "untouched"', '[gate]\nexpr = "untouched"\npattern = "\\s+"'
)
UNBOUND: Final = VALID.replace('expr = "untouched"', 'expr = "untouched and reviewed"')
_SHOW: Final = "\n".join(f"line {n}: gate untouched" for n in range(40)) + "\n"


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write("playbook/prompts/demo.md", _PROMPT)
    pack_repo.write(f"{TASK_DIR}/setup/src/app.py", "x = 1\n")
    pack_repo.write(TASK, VALID)
    pack_repo.install_pack([HOOK_ID])
    return pack_repo


def _show_proc() -> FakeProc:
    proc = FakeProc()
    proc.script(playbook_child("eval"), stdout=_SHOW.encode())
    return proc


def _write(
    repo: PackRepo, deps: RuntimeDeps, rel: str, text: str, state: Path | None = None
) -> SimulateReport:
    repo.write(rel, text)
    tool_input = {"file_path": str(repo.root / rel), "content": text}
    payload = repo.tool_payload("Write", tool_input, event=EventName.POST_TOOL_USE)
    return repo.simulate(payload, deps, event=EventName.POST_TOOL_USE, state=state)


@pytest.mark.parametrize(
    ("harness", "case"),
    [("claude_code", "etl_write_task_bad_escape"), ("opencode", "etl_write_task_bad_escape")],
)
def test_basic_string_backslash_s_gets_literal_string_hint(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    hook_payload: Payload,
    harness: str,
    case: str,
) -> None:
    repo.write(TASK, BAD_ESCAPE)
    golden = hook_payload(harness, "post_tool_use", case)

    report = repo.simulate(
        repo.relocate(golden), deps(), harness=Harness(harness), event=EventName.POST_TOOL_USE
    )

    combined = report.trace.combined
    assert list(combined.context) == golden.expected["result"]["context"]
    assert report.trace.wire == golden.wire()
    [item] = combined.context
    assert "Unescaped" in item and HINT in item


def test_unbound_expr_identifier_reported(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    report = _write(repo, deps(), TASK, UNBOUND)  # FakeProc(): no --show for a broken task

    [item] = report.trace.combined.context
    assert item.startswith('Eval task "demo-task" does not compile')
    assert "reviewed" in item


def test_valid_task_show_excerpt_once_at_most_25_lines(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    proc, clock = _show_proc(), FakeClock()
    shared, state = deps(proc=proc, clock=clock), tmp_path / "state"

    first = _write(repo, shared, TASK, VALID, state)
    clock.advance(5)
    second = _write(repo, shared, TASK, VALID + "\n", state)

    [item] = first.trace.combined.context
    assert item.startswith('How the engine reads eval task "demo-task"')
    assert 1 < len(item.splitlines()) <= 26  # the header plus at most 25 lines
    assert '"line 0: gate untouched"' in item and "line 25" not in item
    assert second.trace.combined.decision is Decision.NONE
    assert playbook_calls(proc) == [("eval", "--show", "demo-task", "--repo-root", str(repo.root))]


def test_setup_pyproject_edit_lints_its_task(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    report = _write(repo, deps(), f"{TASK_DIR}/setup/pyproject.toml", "[project\n")

    [item] = report.trace.combined.context
    assert "setup/pyproject.toml is not valid TOML" in item


def test_runner_and_judge_entry_points_never_loaded(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], monkeypatch: pytest.MonkeyPatch
) -> None:
    groups: list[str | None] = []
    real = importlib.metadata.entry_points

    def spy(**params: Any) -> importlib.metadata.EntryPoints:
        groups.append(params.get("group"))
        return real(**params)

    monkeypatch.setattr(importlib.metadata, "entry_points", spy)

    report = _write(repo, deps(proc=_show_proc()), TASK, VALID)

    assert report.trace.combined.decision is Decision.CONTEXT
    assert not {"coding_agent_playbook.runners", "coding_agent_playbook.judges"} & set(groups)


def test_inert_without_eval_tasks_dir(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    report = _write(repo, deps(), "config/task.toml", 'pattern = "\\s"\n')

    assert report.trace.combined.decision is Decision.NONE


def test_schema_error_names_task_toml_not_the_absolute_path(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    report = _write(repo, deps(), TASK, VALID.replace('prompt_id = "demo"\n', ""))

    [item] = report.trace.combined.context
    assert '"task.toml: ' in item and "prompt_id" in item
    assert str(repo.root) not in item


def test_show_child_failure_is_silent(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    proc = FakeProc()
    proc.script(playbook_child("eval"), returncode=2, stderr=b"error: no config\n")

    report = _write(repo, deps(proc=proc), TASK, VALID)

    assert report.trace.combined.decision is Decision.NONE
    assert len(proc.calls) == 1
