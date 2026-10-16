"""command-convention-guard: a consumer's Bash convention rows; the engine ships none (specs/prK-hook-pack.md §E.4).

Each case installs the opt-in hook with ``[hooks.command-convention-guard]
rules`` and runs a Bash call through ``playbook-hook simulate pre_tool_use``.
The rows mirror this repository's own conventions (``uv run python -m mypy``).
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.decision import Decision
from tests.hook_runtime.fakes import FakeGit

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hooks.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "command-convention-guard"
CORRECTION: Final = "Use `uv run python -m mypy` / `uv run python -m pytest -q`."
DENY_ROW: Final = {"regex": r"^uv run (mypy|pytest)\b", "decision": "deny", "message": CORRECTION}
WARN_ROW: Final = {
    "id": "subset-run",
    "regex": r"(mypy|ruff check|pytest)\s+\S+\.py",
    "decision": "warn",
    "message": "Subset run: fine for iteration, not CI parity.",
}


def _install(repo: PackRepo, *rows: dict[str, Any], prefixes: tuple[str, ...] = ()) -> PackRepo:
    repo.install_pack(
        [HOOK_ID], per_hook={HOOK_ID: {"rules": list(rows)}}, wrapper_prefixes=prefixes
    )
    return repo


def _bash(
    repo: PackRepo,
    deps: Deps,
    command: str,
    *,
    state: Path | None = None,
    git: FakeGit | None = None,
) -> SimulateReport:
    payload = repo.tool_payload("Bash", {"command": command})
    return repo.simulate(payload, deps(git=git or FakeGit()), state=state)


def test_deny_row_carries_correction(pack_repo: PackRepo, deps: Deps) -> None:
    repo = _install(pack_repo, DENY_ROW)

    denied = _bash(repo, deps, "uv run mypy src")
    canonical = _bash(repo, deps, "uv run python -m mypy")

    assert denied.trace.combined.decision is Decision.DENY
    assert denied.trace.combined.reason == CORRECTION
    assert canonical.trace.combined.decision is Decision.NONE


def test_no_rows_means_no_handler_work(pack_repo: PackRepo, deps: Deps) -> None:
    repo = _install(pack_repo)
    git = FakeGit()

    report = _bash(repo, deps, "uv run mypy src", git=git)

    assert report.trace.combined.decision is Decision.NONE
    assert [done.result.rule_id for done in report.trace.ran] == [""]
    assert git.calls == []


def test_warn_row_once_per_session(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    repo = _install(pack_repo, WARN_ROW)
    state = tmp_path / "state"

    first = _bash(repo, deps, "uv run python -m pytest tests/test_a.py", state=state)
    second = _bash(repo, deps, "uv run python -m pytest tests/test_b.py", state=state)

    assert first.trace.combined.decision is Decision.CONTEXT
    assert first.trace.combined.context == ("Subset run: fine for iteration, not CI parity.",)
    assert second.trace.combined.decision is Decision.NONE


def test_proxy_prefix_unwrapped(pack_repo: PackRepo, deps: Deps) -> None:
    repo = _install(pack_repo, DENY_ROW, prefixes=("proxy",))

    report = _bash(repo, deps, "proxy uv run mypy")

    assert report.trace.combined.decision is Decision.DENY


def test_redos_row_fails_validate(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    (repo / ".coding-agent-playbook.toml").write_text(
        'schema_version = 1\nadapters_enabled = ["claude_code"]\noverlays_enabled = []\n\n'
        '[project]\nname = "synthetic"\nkind = "python-library"\n\n'
        '[engine]\nversion = "0.1.0a0"\n\n'
        "[hooks]\nenabled = true\nenable = ['command-convention-guard']\n\n"
        "[hooks.command-convention-guard]\n"
        "rules = [{regex = '(a+)+$', decision = 'deny', message = 'x'}]\n",
        encoding="utf-8",
    )

    code = _validate.run(argparse.Namespace(repo_root=str(repo)))

    fails = [line for line in capsys.readouterr().out.splitlines() if line.startswith("FAIL ")]
    assert code == 1
    assert any(
        "[hooks.command-convention-guard] rules:" in line and "nests unbounded" in line
        for line in fails
    )
