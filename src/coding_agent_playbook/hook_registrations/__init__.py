"""Harness registrations for enabled hooks (specs/prK-lifecycle-hooks.md §C.2.1, §C.2.2, §D.4).

Pure functions from enabled hooks to what a hook-capable adapter registers. A
package so each harness's rendering stays under the file-size budget; import
from here, not from the submodules:

- :mod:`.plan` (harness-neutral): :func:`plan_registrations`, one
  :class:`HookRegistration` per reachable event plus the ``session_start``
  bootstrap, and the one §D.4 timeout formula (:func:`deadlines_ms`,
  :func:`registration_timeout_s`, the checked one-second margin);
- :mod:`.claude`: :func:`to_claude_group` with its matcher union and exact
  launcher command, and :func:`render_claude_launcher`;
- :mod:`.opencode`: :func:`to_opencode_reg`, the OpenCode V1 shim's ``REG``
  over the closed V1 tool vocabulary, :func:`plan_opencode_reg` (§C.3.2), and
  :func:`render_opencode_shim`, the one generated plugin file (§C.3.1);
- :mod:`.stop_gate`: the Stop coordinator's ``guard_config.stop_gate`` table
  (:func:`stop_gate_table`) and the execution-stage timeouts the stop
  deadline adds (prK-hook-pack.md §E.0.5).

The event, tool-class and support tables live in ``hooks.resolution.tables`` (§A.11); this
package only reads them. Stdlib-only. Handler routes (``hook_runtime.routing``,
:func:`member_route`) keep the decision sink out of every registration and put
local-audit-log's ``post_tool_use`` on the one async registration (OQ-19):
Claude's ``async: true`` group and the shim ``REG``'s ``async`` pre-filter.
"""

from __future__ import annotations

from coding_agent_playbook.hook_registrations.claude import (
    LAUNCHER_PATH,
    STOP_STATUS_MESSAGE,
    STRICT_LAUNCH_FLAG,
    claude_command,
    claude_settings_projection,
    matcher_union,
    render_claude_launcher,
    to_claude_group,
)
from coding_agent_playbook.hook_registrations.opencode import (
    OPENCODE_REG_EVENTS,
    OPENCODE_SHIM_PATH,
    OPENCODE_V1_TOOLS,
    REG_PLACEHOLDER,
    OpenCodeRegEntry,
    opencode_reg_json,
    plan_opencode_reg,
    render_opencode_shim,
    to_opencode_reg,
)
from coding_agent_playbook.hook_registrations.plan import (
    BOOTSTRAP_DEADLINE_MS,
    STOP_EVENTS,
    WATCHDOG_MARGIN_MS,
    BoundHandler,
    DeclaredMember,
    HookRegistration,
    RegistrationMember,
    RegistrationTimeoutError,
    checked_registration_timeout_s,
    deadlines_ms,
    declared_stop_budget_s,
    member_route,
    plan_registrations,
    registration_timeout_s,
    resolved_deadlines_ms,
)
from coding_agent_playbook.hook_registrations.stop_gate import (
    STOP_COORDINATOR_ID,
    StageRecord,
    coordinator_budget_s,
    execution_timeouts_s,
    stop_gate_table,
    stop_stage_records,
)

__all__ = [
    "BOOTSTRAP_DEADLINE_MS",
    "LAUNCHER_PATH",
    "OPENCODE_REG_EVENTS",
    "OPENCODE_SHIM_PATH",
    "OPENCODE_V1_TOOLS",
    "REG_PLACEHOLDER",
    "STOP_COORDINATOR_ID",
    "STOP_EVENTS",
    "STOP_STATUS_MESSAGE",
    "STRICT_LAUNCH_FLAG",
    "WATCHDOG_MARGIN_MS",
    "BoundHandler",
    "DeclaredMember",
    "HookRegistration",
    "OpenCodeRegEntry",
    "RegistrationMember",
    "RegistrationTimeoutError",
    "StageRecord",
    "checked_registration_timeout_s",
    "claude_command",
    "claude_settings_projection",
    "coordinator_budget_s",
    "deadlines_ms",
    "declared_stop_budget_s",
    "execution_timeouts_s",
    "matcher_union",
    "member_route",
    "opencode_reg_json",
    "plan_opencode_reg",
    "plan_registrations",
    "registration_timeout_s",
    "render_claude_launcher",
    "render_opencode_shim",
    "resolved_deadlines_ms",
    "stop_gate_table",
    "stop_stage_records",
    "to_claude_group",
    "to_opencode_reg",
]
