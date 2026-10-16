"""The session-start heartbeat line and the canary rows it runs (specs/prK-hook-pack.md §E.1).

The line is at most 40 characters: ``PLAYBOOK-GUARDS: OK <n>`` when every
enabled pre_tool_use guard with a canary row answered as expected, else
``GUARDRAILS DEGRADED: <which>``. A guard without a row is skipped, never
marked degraded. A ``ConfigFault`` on ``session_start`` (the briefing cannot
run at all) still says ``DEGRADED`` to the model.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime._hook_records import parse_hook_record
from coding_agent_playbook.hook_runtime.canary import DEFAULT_CANARIES, enabled_canaries
from coding_agent_playbook.hook_runtime.dispatch import run_event
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.heartbeat import (
    HEARTBEAT_MAX_CHARS,
    degraded_line,
    ok_line,
)
from tests.hook_runtime.guard_repo import hook_record

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from tests.hook_runtime.guard_repo import GuardRepo


def test_ok_and_degraded_lines_fit_forty_characters() -> None:
    assert ok_line(2) == "PLAYBOOK-GUARDS: OK 2"
    assert degraded_line(["config"]) == "GUARDRAILS DEGRADED: config"
    long = degraded_line(["guard-generated-outputs", "control-plane-guard"])
    assert len(long) == HEARTBEAT_MAX_CHARS
    assert long.startswith("GUARDRAILS DEGRADED: guard-generated") and long.endswith("…")


def test_enabled_canaries_keep_rows_of_enabled_pre_tool_use_guards() -> None:
    raw = {
        "guard-generated-outputs": hook_record("guard-generated-outputs"),
        "control-plane-guard": hook_record("control-plane-guard", events=["post_tool_use"]),
        "guard-without-row": hook_record("guard-without-row"),
    }
    hooks = {
        hook_id: parse_hook_record(hook_id, record, platform="linux", home=None)
        for hook_id, record in raw.items()
    }

    rows = enabled_canaries(hooks)

    assert [row.hook_id for row in rows] == ["guard-generated-outputs"]
    assert all(row in DEFAULT_CANARIES for row in rows)


def test_config_fault_on_session_start_reports_degraded_to_the_model(
    repo: GuardRepo, make_deps: Callable[..., RuntimeDeps]
) -> None:
    repo.install(hook_record("guard-a"))
    repo.write_lock("0" * 64)  # guard_config.json changed since sync
    payload = repo.payload(EventName.SESSION_START, source="startup")

    first = run_event(EventName.SESSION_START, Harness.CLAUDE_CODE, payload, make_deps())
    second = run_event(EventName.SESSION_START, Harness.CLAUDE_CODE, payload, make_deps())

    for wire in (first, second):  # every start, resume or compaction: context is not kept
        output = json.loads(wire.stdout)["hookSpecificOutput"]
        assert output["additionalContext"] == "GUARDRAILS DEGRADED: config"
    assert "digest_mismatch" in json.loads(first.stdout)["systemMessage"]
