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
  over the closed V1 tool vocabulary, and :func:`plan_opencode_reg` (§C.3.2).

The event, tool-class and support tables live in ``hook_policy`` (§A.11); this
package only reads them. Stdlib-only. The async ``PostToolUse`` audit
registration (OQ-19) lands with K9, its only consumer.
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
    OPENCODE_V1_TOOLS,
    OpenCodeRegEntry,
    opencode_reg_json,
    plan_opencode_reg,
    to_opencode_reg,
)
from coding_agent_playbook.hook_registrations.plan import (
    BOOTSTRAP_DEADLINE_MS,
    STOP_COORDINATOR_ID,
    STOP_EVENTS,
    WATCHDOG_MARGIN_MS,
    DeclaredMember,
    HookRegistration,
    RegistrationMember,
    RegistrationTimeoutError,
    checked_registration_timeout_s,
    coordinator_budget_s,
    deadlines_ms,
    declared_stop_budget_s,
    plan_registrations,
    registration_timeout_s,
    resolved_deadlines_ms,
)

__all__ = [
    "BOOTSTRAP_DEADLINE_MS",
    "LAUNCHER_PATH",
    "OPENCODE_REG_EVENTS",
    "OPENCODE_V1_TOOLS",
    "STOP_COORDINATOR_ID",
    "STOP_EVENTS",
    "STOP_STATUS_MESSAGE",
    "STRICT_LAUNCH_FLAG",
    "WATCHDOG_MARGIN_MS",
    "DeclaredMember",
    "HookRegistration",
    "OpenCodeRegEntry",
    "RegistrationMember",
    "RegistrationTimeoutError",
    "checked_registration_timeout_s",
    "claude_command",
    "claude_settings_projection",
    "coordinator_budget_s",
    "deadlines_ms",
    "declared_stop_budget_s",
    "matcher_union",
    "opencode_reg_json",
    "plan_opencode_reg",
    "plan_registrations",
    "registration_timeout_s",
    "render_claude_launcher",
    "resolved_deadlines_ms",
    "to_claude_group",
    "to_opencode_reg",
]
