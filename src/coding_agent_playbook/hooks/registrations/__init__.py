"""Harness registrations for enabled hooks (specs/prK-lifecycle-hooks.md §C.2.1, §C.2.2, §D.4).

Deliberately empty: import the defining module. Pure functions from enabled hooks
to what a hook-capable adapter registers, one module per harness so each stays
under the file-size budget:

- :mod:`.plan` (harness-neutral): :func:`plan_registrations`, one
  :class:`HookRegistration` per reachable event plus the ``session_start``
  bootstrap, and the one §D.4 timeout formula (:func:`deadlines_ms`,
  :func:`registration_timeout_s`, the checked one-second margin);
- :mod:`.claude`: :func:`to_claude_group` with its matcher union and exact
  launcher command, and :func:`render_claude_launcher`;
- :mod:`.launcher`: the committed launcher's path and its ownership token, a
  stdlib leaf the Claude Code settings merge shares;
- :mod:`.opencode`: :func:`to_opencode_reg`, the OpenCode V1 shim's ``REG``
  over the closed V1 tool vocabulary, :func:`plan_opencode_reg` (§C.3.2), and
  :func:`render_opencode_shim`, the one generated plugin file (§C.3.1);
- :mod:`.stop_gate`: the Stop coordinator's ``guard_config.stop_gate`` table
  (:func:`stop_gate_table`) and the execution-stage timeouts the stop
  deadline adds (prK-hook-pack.md §E.0.5).

The shim templates they fill are package data under ``templates/`` here. The
event, tool-class and support tables live in ``hooks.resolution.tables`` (§A.11);
this package only reads them. Stdlib-only. Handler routes
(``hook_runtime.dispatch.routing``, :func:`member_route`) keep the decision sink out of
every registration and put local-audit-log's ``post_tool_use`` on the one async
registration (OQ-19): Claude's ``async: true`` group and the shim ``REG``'s
``async`` pre-filter.
"""
