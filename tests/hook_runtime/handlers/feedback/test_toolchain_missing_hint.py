"""toolchain-missing-hint: name the project's install command when a dev tool is missing (specs/prK-hook-pack.md §E.3).

The install hint is derived at sync from the detected package manager and the
repository's pyproject (``hooks.guard_config._tables_toolchain``); the hook only matches
the Bash output and says it once per session per tool. Every case runs the
shipped ``HOOK.md`` through ``playbook-hook simulate``; nothing spawns.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness
from coding_agent_playbook.hook_runtime.handlers.toolchain import missing_tool
from coding_agent_playbook.hooks.guard_config.inputs import DetectInputs
from tests.hook_runtime.handlers.pack_repo import engine_hook

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "toolchain-missing-hint"
UV_EXTRA: Final = '[project]\nname = "app"\n[project.optional-dependencies]\ndev = ["mypy"]\n'
NO_MYPY: Final = "Exit code 1\n/usr/bin/python3: No module named mypy"


def _hint(tool: str, command: str) -> str:
    return (
        f"Dev tooling is not installed in this environment (`{tool}` is missing). "
        f"The project installs it with `{command}`. Ask the user before installing "
        "(it may contact the package index)."
    )


def _install(repo: PackRepo, pyproject: str = UV_EXTRA, manager: str = "uv") -> None:
    repo.write("pyproject.toml", pyproject)
    repo.install_pack([HOOK_ID], detect=DetectInputs(facts={"package_manager": manager}))


def _failure(
    repo: PackRepo, deps: RuntimeDeps, error: str = NO_MYPY, *, state: Path | None = None
) -> SimulateReport:
    event = EventName.POST_TOOL_USE_FAILURE
    payload = repo.tool_payload("Bash", {"command": "python -m mypy src"}, event=event, error=error)
    return repo.simulate(payload, deps, event=event, state=state)


def _success(repo: PackRepo, deps: RuntimeDeps, **response: Any) -> SimulateReport:
    event = EventName.POST_TOOL_USE
    payload = repo.tool_payload(
        "Bash", {"command": "make check"}, event=event, tool_response=dict(response)
    )
    return repo.simulate(payload, deps, event=event)


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    """A uv project with a ``dev`` extra; the hook on."""
    _install(pack_repo)
    return pack_repo


def test_failure_no_module_named_mypy_hints_uv_sync_extra_dev(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload
) -> None:
    case = hook_payload("claude_code", "post_tool_use_failure", "tmh_no_module_mypy")

    report = repo.simulate(
        repo.relocate(case), deps(), harness=Harness.CLAUDE_CODE, event=case.event_name
    )

    combined, expected = report.trace.combined, case.expected["result"]
    assert (combined.decision.value, list(combined.context)) == (
        expected["decision"],
        expected["context"],
    )
    assert list(combined.context) == [_hint("mypy", "uv sync --extra dev")]
    assert report.trace.wire == case.wire()


def test_second_time_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    state = tmp_path / "state"

    first = _failure(repo, deps(), state=state)
    second = _failure(repo, deps(), state=state)
    other_tool = _failure(repo, deps(), "Exit code 127\nbash: ruff: command not found", state=state)

    assert first.trace.combined.decision is Decision.CONTEXT
    assert second.trace.combined.decision is Decision.NONE  # once per session per tool
    assert list(other_tool.trace.combined.context) == [_hint("ruff", "uv sync --extra dev")]


def test_successful_command_silent(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    report = _success(repo, deps(), stdout="3 passed", stderr="")

    assert report.trace.combined.decision is Decision.NONE


def test_successful_output_naming_a_missing_tool_hints(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    """A later segment can succeed after an earlier ``command not found``."""
    report = _success(repo, deps(), stdout="done", stderr="zsh: command not found: pytest")

    assert list(report.trace.combined.context) == [_hint("pytest", "uv sync --extra dev")]


def test_poetry_fixture_hint(pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    poetry = '[tool.poetry]\nname = "app"\n[tool.poetry.group.dev.dependencies]\nmypy = "*"\n'
    _install(pack_repo, poetry, manager="poetry")

    report = _failure(pack_repo, deps())

    assert list(report.trace.combined.context) == [_hint("mypy", "poetry install --with dev")]


def test_dependency_group_hint_uses_uv_sync_group_dev(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    _install(pack_repo, '[project]\nname = "app"\n[dependency-groups]\ndev = ["mypy"]\n')

    report = _failure(pack_repo, deps())

    assert list(report.trace.combined.context) == [_hint("mypy", "uv sync --group dev")]


@pytest.mark.parametrize(
    ("dev", "advice"),
    [
        ('["mypy"]', "Ask the user to install commitizen (`pipx install commitizen`)."),
        ('["mypy", "commitizen>=3"]', "installs it with `uv sync --extra dev`"),
    ],
    ids=["not-pinned", "dev-extra"],
)
def test_cz_hint_names_the_dev_extra_only_when_commitizen_is_in_it(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], dev: str, advice: str
) -> None:
    _install(pack_repo, f'[project]\nname = "app"\n[project.optional-dependencies]\ndev = {dev}\n')

    report = _failure(pack_repo, deps(), "Exit code 127\nbash: cz: command not found")

    [line] = report.trace.combined.context
    assert advice in line


def test_install_hint_is_rendered_into_both_event_configs(pack_repo: PackRepo) -> None:
    _install(pack_repo)

    record = json.loads(
        (pack_repo.root / ".coding-agent-playbook/hooks/guard_config.json").read_text()
    )["hooks"][HOOK_ID]

    configs = [
        record["handlers"][event]["config"] for event in ("post_tool_use", "post_tool_use_failure")
    ]
    assert configs == [{"cz_install_hint": "", "install_hint": "uv sync --extra dev"}] * 2


@pytest.mark.parametrize(
    ("text", "tool"),
    [
        ("ModuleNotFoundError: No module named 'pytest'", "pytest"),
        ("No module named commitizen", "cz"),
        ("No module named 'pytest_asyncio'", None),
        ("ruff 0.15.0", None),
        ("x" * 9000 + "\nmypy: command not found", "mypy"),
        (None, None),
    ],
)
def test_missing_tool_regex(text: str | None, tool: str | None) -> None:
    assert missing_tool(text) == tool


def test_hook_md_matches_its_pack_row_and_handler(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§E.0.6 row 22: default, post_tool_use (+ _failure), inject_context -> context, open."""
    fm = engine_hook(HOOK_ID).frontmatter

    rc = _validate.run(argparse.Namespace(repo_root=str(tmp_path)))

    assert (fm.tier, fm.events, fm.decisions, fm.on_error) == (
        "default",
        ["post_tool_use", "post_tool_use_failure"],
        ["context", "none"],
        "open",
    )
    assert fm.matcher["post_tool_use_failure"].tools == ["shell"]
    assert fm.handler is not None and fm.handler.builtin == "toolchain_hint"
    assert fm.supports == ["claude_code", "opencode"]  # OQ-43: the failure event degrades there
    assert rc == 0
    assert HOOK_ID not in capsys.readouterr().err
