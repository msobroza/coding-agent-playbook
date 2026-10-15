"""The import-light contract of the dispatch hot path (specs/prK-lifecycle-hooks.md §D.1, D-6).

Each case runs the real harness entry, ``python -I -X importtime -m
coding_agent_playbook.hook_runtime dispatch ...``, in a fresh interpreter
against a synced fixture repo, and reads every imported module from the
``importtime`` report. The hot path (``pre_tool_use`` for an Edit and for a
Bash command, and ``post_tool_use`` after a Python edit) may import only the
stdlib, ``hook_runtime.*`` and ``security.*``; ``tomllib`` loads only on
``session_start`` or when the lockfile's stat changed (§D.8.1). P-D1 (the lazy
``__version__``) is what keeps ``importlib.metadata`` off this path. The first
pack guard (guard-generated-outputs, Track K5) denies a protected edit from the
rendered tables alone: no TOML, no render, no subprocess. control-plane-guard
loads its JSON/TOML/text verdict modules only on their branch, and ``tomllib``
only for an edit of a ``.toml`` policy file (§D.1's branch-local row).
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook._sentinel import SENTINEL, sentinel_line
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.harness import DENY_EXIT
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


def _imports(
    proc: SubprocessProc,
    repo: GuardRepo,
    event: EventName,
    payload: bytes,
    *,
    exit_code: int = 0,
) -> set[str]:
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
    assert result.returncode == exit_code, result.stderr.decode()
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


_PROTECTED_MODULE: Final = "coding_agent_playbook.hook_runtime.protected"


@pytest.fixture
def guarded(tmp_path: Path, real_proc: SubprocessProc) -> GuardRepo:
    """A synced repo with guard-generated-outputs bound to its real builtin (warm digest)."""
    repo = GuardRepo.create(tmp_path)
    claude_md = repo.root / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir()
    claude_md.write_text(f"{sentinel_line('html')}\n# Rules\n", encoding="utf-8")
    ggo = hook_record(
        "guard-generated-outputs",
        decisions=("deny", "ask", "none"),
        matcher={"pre_tool_use": {"tools": ["edit", "write", "notebook_edit", "shell"]}},
    )
    row = {"path": ".claude/CLAUDE.md", "kind": "composite", "artifact_id": "", "source": ""}
    protected = {
        "entries": [{**row, "scope": ""}],
        "output_dirs": [".claude/CLAUDE.md", ".claude/commands/"],
        "hook_artifacts": [".coding-agent-playbook/hooks/"],
        "resource_roots": ["pkg:coding_agent_playbook/resources"],
    }
    repo.install(ggo, sentinel=SENTINEL, protected=protected)
    start = repo.payload(EventName.SESSION_START, source="startup")
    _imports(real_proc, repo, EventName.SESSION_START, start)
    return repo


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Edit", {"file_path": ".claude/CLAUDE.md", "old_string": "a", "new_string": "b"}),
        ("Bash", {"command": "echo x > .claude/CLAUDE.md"}),
    ],
    ids=["edit", "bash-redirect"],
)
def test_protected_edit_denied_without_toml_render_or_subprocess(
    guarded: GuardRepo, real_proc: SubprocessProc, tool: str, tool_input: dict[str, str]
) -> None:
    payload = guarded.payload(EventName.PRE_TOOL_USE, tool_name=tool, tool_input=tool_input)

    imported = _imports(real_proc, guarded, EventName.PRE_TOOL_USE, payload, exit_code=DENY_EXIT)

    # ``registry`` loads the handler through ``importlib.import_module``, which
    # ``-X importtime`` does not report; ``protected`` is imported only by it.
    assert _PROTECTED_MODULE in imported  # the guard ran (and denied: exit 10)
    assert _forbidden(imported) == []
    assert "subprocess" not in imported
    assert "coding_agent_playbook.hook_runtime.pin" not in imported  # no machine.json read


_CPG_PREFIX: Final = "coding_agent_playbook.hook_runtime.handlers._control_plane_"


@pytest.fixture
def control_planed(tmp_path: Path, real_proc: SubprocessProc) -> GuardRepo:
    """A synced repo with control-plane-guard bound to its real builtin (warm digest)."""
    repo = GuardRepo.create(tmp_path)
    (repo.root / "src").mkdir()
    (repo.root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    config = '[project]\nname = "demo"\ndescription = "A demo"\n'
    (repo.root / ".coding-agent-playbook.toml").write_text(config, encoding="utf-8")
    (repo.root / ".mcp.json").write_text('{"mcpServers": {}}\n', encoding="utf-8")
    cpg = hook_record(
        "control-plane-guard",
        decisions=("deny", "ask", "none"),
        matcher={"pre_tool_use": {"tools": ["edit", "write", "shell"]}},
    )
    repo.install(cpg)
    start = repo.payload(EventName.SESSION_START, source="startup")
    _imports(real_proc, repo, EventName.SESSION_START, start)
    return repo


def _edit_payload(repo: GuardRepo, rel: str, old: str, new: str) -> bytes:
    tool_input = {"file_path": rel, "old_string": old, "new_string": new}
    return repo.payload(EventName.PRE_TOOL_USE, tool_name="Edit", tool_input=tool_input)


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Edit", {"file_path": "src/app.py", "old_string": "x = 1", "new_string": "x = 2"}),
        ("Bash", {"command": "ls -la && playbook sync"}),
    ],
    ids=["edit-py", "plain-bash"],
)
def test_control_plane_guard_loads_nothing_new_off_its_files(
    control_planed: GuardRepo, real_proc: SubprocessProc, tool: str, tool_input: dict[str, str]
) -> None:
    payload = control_planed.payload(EventName.PRE_TOOL_USE, tool_name=tool, tool_input=tool_input)

    imported = _imports(real_proc, control_planed, EventName.PRE_TOOL_USE, payload)

    assert f"{_CPG_PREFIX}paths" in imported  # the guard ran (its routing table loaded)
    assert _forbidden(imported) == []
    assert sorted(m for m in imported if m.startswith(_CPG_PREFIX)) == [
        f"{_CPG_PREFIX}paths",
        f"{_CPG_PREFIX}shell",
        f"{_CPG_PREFIX}toml",  # the policy key rows only: tomllib stays unloaded
    ]
    assert "subprocess" not in imported


def test_tomllib_loads_only_for_a_toml_policy_edit(
    control_planed: GuardRepo, real_proc: SubprocessProc
) -> None:
    toml_edit = _edit_payload(control_planed, ".coding-agent-playbook.toml", "A demo", "B demo")
    json_edit = _edit_payload(control_planed, ".mcp.json", "{}", '{"x": {"command": "x"}}')

    on_toml = _imports(real_proc, control_planed, EventName.PRE_TOOL_USE, toml_edit)
    on_json = _imports(real_proc, control_planed, EventName.PRE_TOOL_USE, json_edit)

    assert "tomllib" in on_toml
    assert _forbidden(on_toml, allowed=("tomllib",)) == []
    assert "tomllib" not in on_json
    assert f"{_CPG_PREFIX}json" in on_json
    assert _forbidden(on_json) == []
