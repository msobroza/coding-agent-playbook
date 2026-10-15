"""The Stop coordinator stays import-light (specs/prK-lifecycle-hooks.md §D.1, prK-hook-pack.md §E.2).

A real ``dispatch stop`` in a fresh interpreter, with the coordinator and the
``drift`` stage hook bound to their builtins: the coordinator and its stage
planning load, an inactive stage loads nothing of its own, and no forbidden
module (jinja2, yaml, tomllib without an active stage, the CLI, the
renderers, ``evaluators``) is imported. The helpers are
``test_import_budget``'s, so both files read the same ``importtime`` report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime.event import EventName
from tests.hook_runtime.guard_repo import GuardRepo, hook_record
from tests.hook_runtime.test_import_budget import _forbidden, _imports

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.proc import SubprocessProc

_COORDINATOR = "coding_agent_playbook.hook_runtime.stop.coordinator"


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
    assert "coding_agent_playbook.hook_runtime.handlers._drift" not in imported  # inactive stage
    assert _forbidden(imported) == []
