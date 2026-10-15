"""The import-light contract of the dispatch hot path (specs/prK-lifecycle-hooks.md §D.1, D-6).

Each case runs the real harness entry, ``python -I -X importtime -m
coding_agent_playbook.hook_runtime dispatch ...``, in a fresh interpreter
against a synced fixture repo, and reads every imported module from the
``importtime`` report. The hot path (``pre_tool_use`` for an Edit and for a
Bash command, and ``post_tool_use`` after a Python edit) may import only the
stdlib, ``hook_runtime.*`` and ``security.*``; ``tomllib`` loads only on
``session_start`` or when the lockfile's stat changed (§D.8.1). P-D1 (the lazy
``__version__``) is what keeps ``importlib.metadata`` off this path.
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.hook_runtime.event import EventName
from tests.hook_runtime.guard_repo import GuardRepo, hook_record
from tests.import_probe import PROBE_TIMEOUT_S, probe_env

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.proc import SubprocessProc

FORBIDDEN: Final = (
    "jinja2",
    "yaml",
    "importlib.metadata",
    "tomllib",
    "packaging",
    "argparse",
    *(
        f"coding_agent_playbook.{name}"
        for name in (
            "cli",
            "renderer",
            "orchestrator",
            "adapters",
            "sources",
            "commands",
            "evaluators",
            "evals",
            "detector",
        )
    ),
)
_IMPORT_LINE: Final = re.compile(r"^import time:\s+\d+ \|\s+\d+ \|\s*(\S+)\s*$")


def _imports(proc: SubprocessProc, repo: GuardRepo, event: EventName, payload: bytes) -> set[str]:
    argv = [
        sys.executable,
        "-I",
        "-X",
        "importtime",
        "-m",
        "coding_agent_playbook.hook_runtime",
        "dispatch",
        event.value,
        "--harness",
        "claude_code",
    ]
    env = {**probe_env(), "CLAUDE_PROJECT_DIR": str(repo.root)}
    result = proc.run(argv, timeout=PROBE_TIMEOUT_S, env=env, input=payload, cwd=str(repo.root))
    assert result.returncode == 0, result.stderr.decode()
    lines = result.stderr.decode("utf-8", "replace").splitlines()
    return {m.group(1) for line in lines if (m := _IMPORT_LINE.match(line))}


def _forbidden(imported: set[str], allowed: tuple[str, ...] = ()) -> list[str]:
    return sorted(
        name
        for name in imported
        for banned in FORBIDDEN
        if banned not in allowed and (name == banned or name.startswith(f"{banned}."))
    )


@pytest.fixture
def synced(tmp_path: Path, real_proc: SubprocessProc) -> GuardRepo:
    """A synced repo whose digest cache is warm (one ``session_start`` already ran)."""
    repo = GuardRepo.create(tmp_path)
    (repo.root / "src").mkdir()
    repo.install(
        hook_record("guard-a", events=["pre_tool_use", "post_tool_use"], on_error="ask"),
        hook_record("lint-q", events=["post_tool_use"], on_error="open"),
        path_classes={"py": ["*.py"]},
    )
    start = repo.payload(EventName.SESSION_START, source="startup")
    _imports(real_proc, repo, EventName.SESSION_START, start)
    return repo


@pytest.mark.parametrize(
    ("event", "tool"),
    [
        (EventName.PRE_TOOL_USE, "Edit"),
        (EventName.PRE_TOOL_USE, "Bash"),
        (EventName.POST_TOOL_USE, "Edit"),
    ],
    ids=["pre_tool_use-edit-py", "pre_tool_use-bash", "post_tool_use-python-edit"],
)
def test_hot_path_branches_import_no_forbidden_module(
    synced: GuardRepo, real_proc: SubprocessProc, event: EventName, tool: str
) -> None:
    imported = _imports(real_proc, synced, event, synced.payload(event, tool=tool))

    assert "coding_agent_playbook.hook_runtime.dispatch" in imported
    assert _forbidden(imported) == []


def test_bash_without_git_spawns_no_process_module(
    synced: GuardRepo, real_proc: SubprocessProc
) -> None:
    payload = synced.payload(EventName.PRE_TOOL_USE, tool="Bash")

    imported = _imports(real_proc, synced, EventName.PRE_TOOL_USE, payload)

    assert "subprocess" not in imported
    assert "coding_agent_playbook.hook_runtime.git" not in imported


def test_tomllib_loads_only_on_session_start_or_lock_stat_change(
    synced: GuardRepo, real_proc: SubprocessProc
) -> None:
    pre = synced.payload(EventName.PRE_TOOL_USE, tool="Edit")
    start = synced.payload(EventName.SESSION_START, source="resume")

    warm = _imports(real_proc, synced, EventName.PRE_TOOL_USE, pre)
    lock = synced.root / ".coding-agent-playbook.lock"
    lock.write_text(lock.read_text() + "\n", encoding="utf-8")
    changed = _imports(real_proc, synced, EventName.PRE_TOOL_USE, pre)
    rewarmed = _imports(real_proc, synced, EventName.PRE_TOOL_USE, pre)
    session_start = _imports(real_proc, synced, EventName.SESSION_START, start)

    assert "tomllib" not in warm
    assert "tomllib" in changed
    assert "tomllib" not in rewarmed
    assert "tomllib" in session_start
    assert _forbidden(session_start, allowed=("tomllib",)) == []


def test_the_import_probe_reads_the_importtime_report(
    synced: GuardRepo, real_proc: SubprocessProc
) -> None:
    """Guards the parser above: a report it cannot read would make every assertion vacuous."""
    imported = _imports(
        real_proc, synced, EventName.STOP, synced.payload(EventName.STOP, stop_hook_active=False)
    )

    assert {"json", "coding_agent_playbook.hook_runtime.cli"} <= imported
