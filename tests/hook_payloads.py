"""Golden harness payloads for the hook tests (specs/prK-lifecycle-hooks.md §D.9).

Each case is ``tests/fixtures/hook_payloads/<harness>/<event>/<case>.json``
(the payload, verbatim, with a ``_fixture`` provenance key the parsers ignore)
plus ``<case>.expected.json``:

- ``context``: how to parse it: ``env``, ``project_dir``, ``platform`` (default
  ``linux``), ``truncated``, and ``repo`` (default true: the project dir is a
  repository root, via :func:`fixture_repo_finder`, so goldens never depend on
  the host's filesystem);
- exactly one of ``parsed`` (the :func:`project_event` view), ``foreign`` (the
  inert marker) or ``fault`` (a substring of the ``ContractFault`` problem);
- ``result`` and ``wire``: a combined result to render, and the exact
  ``WireOutput`` it renders to (``wire`` alone for a foreign payload: nothing).

Plain functions, not fixtures, so parametrize lists can call them at import
time; the root ``hook_payload`` fixture serves :func:`load_hook_payload`.
Fixture paths live under ``/playbook-fixture``, which exists on no host, so
``realpath`` leaves them alone on Linux and macOS alike.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.dispatch.decision import CombinedResult, Decision
from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, EventName, RepoInfo
from coding_agent_playbook.hook_runtime.harness.wire import (
    ContractFault,
    ForeignPayload,
    ParseContext,
    ParseOutcome,
    WireOutput,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.dispatch.event import ToolCall
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath

    type Renderer = Callable[[EventName, CombinedResult], WireOutput]

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "hook_payloads"
PROJECT_DIR = "/playbook-fixture/proj"
HOME = "/playbook-fixture/home"
_DEFAULT_CONTEXT: dict[str, Any] = {
    "env": {"CLAUDE_PROJECT_DIR": PROJECT_DIR},
    "project_dir": None,
    "platform": "linux",
    "truncated": False,
    "repo": True,
}
_EXPECTED_SUFFIX = ".expected.json"


@dataclass(frozen=True)
class HookPayloadCase:
    """One golden payload and what it must parse and render to.

    Example::

        case = load_hook_payload("claude_code", "pre_tool_use", "bash_rm_root")
        parse_claude(case.raw, case.parse_context())
    """

    harness: str
    event: str
    case: str
    raw: bytes
    expected: dict[str, Any] = field(default_factory=dict)

    @property
    def event_name(self) -> EventName:
        return EventName(self.event)

    @property
    def context(self) -> dict[str, Any]:
        """The parse context, with the defaults filled in."""
        return {**_DEFAULT_CONTEXT, **self.expected.get("context", {})}

    def parse_context(self) -> ParseContext:
        """The ``ParseContext`` this case is parsed under."""
        ctx = self.context
        return ParseContext(
            argv_event=self.event_name,
            env=dict(ctx["env"]),
            project_dir=ctx["project_dir"],
            home=HOME,
            platform=ctx["platform"],
            truncated=ctx["truncated"],
            find_repo=fixture_repo_finder if ctx["repo"] else _no_repo,
        )

    def combined(self) -> CombinedResult:
        """The ``result`` to render, as a ``CombinedResult``."""
        result = self.expected["result"]
        return CombinedResult(
            decision=Decision(result.get("decision", "none")),
            reason=result.get("reason", ""),
            context=tuple(result.get("context", ())),
            user_notes=tuple(result.get("user_notes", ())),
        )

    def wire(self) -> WireOutput:
        """The exact expected ``WireOutput``."""
        return WireOutput(**self.expected["wire"])


def load_hook_payload(harness: str, event: str, case: str) -> HookPayloadCase:
    """Load ``<harness>/<event>/<case>.json`` and its expected file, if any.

    Example::

        >>> load_hook_payload("claude_code", "stop", "block_chain").event
        'stop'
    """
    directory = FIXTURE_ROOT / harness / event
    expected_path = directory / f"{case}{_EXPECTED_SUFFIX}"
    expected = json.loads(expected_path.read_text("utf-8")) if expected_path.exists() else {}
    return HookPayloadCase(
        harness, event, case, (directory / f"{case}.json").read_bytes(), expected
    )


def hook_payload_cases(harness: str) -> list[tuple[str, str]]:
    """Every ``(event, case)`` of ``harness``, sorted, for parametrize lists."""
    root = FIXTURE_ROOT / harness
    return sorted(
        (path.parent.name, path.name.removesuffix(".json"))
        for path in root.glob("*/*.json")
        if not path.name.endswith(_EXPECTED_SUFFIX)
    )


def check_golden(case: HookPayloadCase, outcome: ParseOutcome, render: Renderer) -> None:
    """Assert that ``outcome`` (the parse of ``case.raw``) and its rendering match ``case``.

    Example::

        check_golden(case, parse_claude(case.raw, case.parse_context()), render_claude)
    """
    expected = case.expected
    if "foreign" in expected:
        assert isinstance(outcome, ForeignPayload), outcome
        assert outcome.marker == expected["foreign"]
        assert case.wire() == WireOutput()
    elif "fault" in expected:
        assert isinstance(outcome, ContractFault), outcome
        assert expected["fault"] in outcome.problem
    else:
        assert isinstance(outcome, CanonicalEvent), outcome
        assert project_event(outcome) == expected["parsed"]
        assert render(case.event_name, case.combined()) == case.wire()


def fixture_repo_finder(start: str) -> RepoInfo:
    """A ``find_repo`` stand-in for which ``start`` is a repository root.

    Example::

        >>> fixture_repo_finder("/p").git_dir
        '/p/.git'
    """
    return RepoInfo(
        worktree_root=start,
        git_dir=f"{start}/.git",
        common_dir=f"{start}/.git",
        is_linked_worktree=False,
    )


def _no_repo(_start: str) -> None:
    return None


def project_event(ev: CanonicalEvent) -> dict[str, Any]:
    """The host-independent golden view of a parsed event (``None`` fields omitted).

    Example::

        >>> project_event(ev)["name"]  # doctest: +SKIP
        'pre_tool_use'
    """
    view: dict[str, Any] = {
        "name": ev.name.value,
        "harness": ev.harness.value,
        "session_id": ev.session_id,
        "turn_id": ev.turn_id,
        "cwd": ev.cwd,
        "project_dir": ev.project_dir,
        "repo_root": ev.repo.worktree_root if ev.repo else None,
        "permission_mode": ev.permission_mode,
        "agent_id": ev.agent_id,
        "agent_type": ev.agent_type,
        "prompt": ev.prompt,
        "source": ev.source,
        "transcript_path": ev.transcript_path,
        "unattended": ev.unattended,
        "truncated": ev.truncated,
        "raw_event_name": ev.raw_event_name,
        "stop": _drop_none(
            {
                "stop_hook_active": ev.stop.stop_hook_active,
                "last_assistant_message": ev.stop.last_assistant_message,
                "agent_transcript_path": ev.stop.agent_transcript_path,
            }
        )
        if ev.stop
        else None,
        "tool": _project_tool(ev.tool) if ev.tool else None,
    }
    return _drop_none(view)


def _project_tool(tool: ToolCall) -> dict[str, Any]:
    command = tool.command
    return _drop_none(
        {
            "name": tool.name,
            "native_name": tool.native_name,
            "tool_class": tool.tool_class.value,
            "tool_classes": sorted(cls.value for cls in tool.tool_classes),
            "use_id": tool.use_id,
            "paths": [_project_path(p) for p in tool.paths],
            "write_paths": [_project_path(p) for p in tool.write_paths],
            "content": [[c.path, c.field, c.text] for c in tool.content],
            "mcp_server": tool.mcp_server,
            "response": _drop_none(
                {
                    "ok": tool.response.ok,
                    "exit_code": tool.response.exit_code,
                    "error": tool.response.error,
                    "is_interrupt": tool.response.is_interrupt,
                }
            )
            if tool.response
            else None,
            "command": {
                "kind": command.kind,
                "parse_error": command.parse_error,
                "segments": [[list(s.argv), s.cwd] for s in command.segments],
            }
            if command
            else None,
        }
    )


def _project_path(path: NormalizedPath) -> dict[str, Any]:
    return _drop_none({"path": path.path, "repo_rel": path.repo_rel, "key": path.key})


def _drop_none(view: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in view.items() if value is not None}
