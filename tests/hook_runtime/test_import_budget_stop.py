"""The Stop coordinator stays import-light (specs/prK-lifecycle-hooks.md §D.1, prK-hook-pack.md §E.2).

A real ``dispatch stop`` in a fresh interpreter, with the coordinator and the
``drift`` stage hook bound to their builtins: the coordinator and its stage
planning load, an inactive stage loads nothing of its own, and no forbidden
module (jinja2, yaml, tomllib without an active stage, the CLI, the
renderers, ``evaluators``) is imported. K6's §D.1 rows: ``metrics_gate.run``
loads only once ``quality-metrics`` measures something, and ``gate_scan`` only
when ``gate-integrity`` scans or gate-weakening-guard's ``pre_edit`` companion
judges a test-file edit, never ``tomllib`` on that ``pre_tool_use`` path. The
helpers are ``test_import_budget``'s, so both files read the same report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.event import EventName
from tests.engine_modules import engine_module
from tests.hook_runtime.guard_repo import GuardRepo, hook_record
from tests.hook_runtime.test_import_budget import _DRIFT_FAST_PATH, _forbidden, _imports
from tests.hooks.stop_kit import TREE

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.proc import SubprocessProc

_COORDINATOR = engine_module("coding_agent_playbook.hook_runtime.stop.coordinator")
_GATE_SCAN = engine_module("coding_agent_playbook.gate_scan")
_GATE_SCAN_FILES = engine_module("coding_agent_playbook._gate_scan_files")
_METRICS_GATE = engine_module("coding_agent_playbook.metrics_gate.run")


def test_stop_coordinator_imports_no_forbidden_module(
    tmp_path: Path, real_proc: SubprocessProc
) -> None:
    repo = GuardRepo.create(tmp_path)
    builtin = {"kind": "builtin", "name": "stop_ci_parity_gate"}
    coordinator = hook_record(
        "stop-ci-parity-gate",
        events=["stop"],
        decisions=("deny", "none"),
        on_error="open",
        handler=builtin,
    )
    drift = hook_record(
        "stop-drift-and-orphan-gate",
        events=["stop"],
        decisions=("deny", "none"),
        on_error="open",
        handler={
            "kind": "builtin",
            "name": "stop_drift_and_orphan_gate",
            "config": {"stage": "drift"},
        },
    )
    repo.install(coordinator, drift, path_classes={"py": ["*.py"]})
    _imports(real_proc, repo, EventName.SESSION_START, repo.payload(EventName.SESSION_START))

    imported = _imports(
        real_proc, repo, EventName.STOP, repo.payload(EventName.STOP, stop_hook_active=False)
    )

    assert _COORDINATOR in imported
    assert _DRIFT_FAST_PATH not in imported  # inactive stage
    assert _forbidden(imported) == []


def _stage_hook(hook_id: str, builtin: str, stage: str, **fields: Any) -> dict[str, Any]:
    handler = {"kind": "builtin", "name": builtin, "config": {"stage": stage}}
    return hook_record(hook_id, decisions=("deny", "ask", "none"), handler=handler, **fields)


def _k6_repo(tmp_path: Path, real_proc: SubprocessProc) -> GuardRepo:
    """The coordinator plus the two K6 stage hooks; the companion bound on ``pre_tool_use``."""
    repo = GuardRepo.create(tmp_path)
    coordinator = hook_record(
        "stop-ci-parity-gate",
        events=["stop"],
        decisions=("deny", "none"),
        on_error="open",
        handler={"kind": "builtin", "name": "stop_ci_parity_gate"},
    )
    metrics = _stage_hook(
        "clean-code-metrics-nonregression",
        "clean_code_metrics_nonregression",
        "quality-metrics",
        events=["stop"],
        on_error="open",
    )
    gate = _stage_hook(
        "gate-weakening-guard",
        "gate_weakening_guard",
        "gate-integrity",
        events=["stop", "pre_tool_use"],
    )
    gate["handlers"]["pre_tool_use"] = {"kind": "builtin", "name": "gate_weakening_guard:pre_edit"}
    tests = ["tests/", "test_*.py", "*_test.py", "conftest.py"]
    repo.install(coordinator, metrics, gate, path_classes={"py": ["*.py"], "test": tests})
    _imports(real_proc, repo, EventName.SESSION_START, repo.payload(EventName.SESSION_START))
    return repo


def test_k6_stop_stages_load_neither_metrics_gate_nor_gate_scan_when_idle(
    tmp_path: Path, real_proc: SubprocessProc
) -> None:
    repo = _k6_repo(tmp_path, real_proc)  # no git history: nothing measured, nothing scanned

    imported = _imports(
        real_proc, repo, EventName.STOP, repo.payload(EventName.STOP, stop_hook_active=False)
    )

    # importlib.import_module loads the handler modules unreported; stop.alone is theirs alone
    assert "coding_agent_playbook.hook_runtime.stop.alone" in imported
    assert {_METRICS_GATE, _GATE_SCAN}.isdisjoint(imported)
    assert _forbidden(imported) == []


def test_pre_edit_companion_loads_gate_scan_only_for_test_paths(
    tmp_path: Path, real_proc: SubprocessProc
) -> None:
    repo = _k6_repo(tmp_path, real_proc)
    (repo.root / "tests").mkdir()
    (repo.root / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")

    def edit(rel: str) -> bytes:
        tool_input = {
            "file_path": str(repo.root / rel),
            "old_string": "def test_a():",
            "new_string": f"@pytest.mark.skip\ndef test_a():  # {TREE[:4]}",
        }
        return repo.payload(
            EventName.PRE_TOOL_USE, tool_name="Edit", tool_input=tool_input, tool_use_id="t1"
        )

    source = _imports(real_proc, repo, EventName.PRE_TOOL_USE, edit("src/a.py"))
    test = _imports(real_proc, repo, EventName.PRE_TOOL_USE, edit("tests/test_a.py"))

    assert _GATE_SCAN not in source
    assert _GATE_SCAN in test
    assert "tomllib" not in source | test
    assert _forbidden(source) == []
    assert _forbidden(test, allowed=(_GATE_SCAN, _GATE_SCAN_FILES)) == []
