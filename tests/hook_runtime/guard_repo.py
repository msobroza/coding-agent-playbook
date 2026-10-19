"""A repository a dispatch can run in, for the in-process pipeline tests (specs/prK-lifecycle-hooks.md §D.9).

:class:`GuardRepo` writes what ``playbook sync`` would: a ``.git/`` dir (found
without git, like ``paths.find_repo``), ``guard_config.json`` in its canonical
serialization, and the lockfile entry whose sha256 vouches for it. Payloads
are Claude-shaped (the OpenCode shim sends the same shape), and
:func:`hook_record` builds one ``guard_config.hooks.<id>`` record in the exact
``ResolvedHook.to_json()`` schema.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.config.schema import GUARD_CONFIG_REL, LOCKFILE_REL
from coding_agent_playbook.hook_runtime.event import RepoInfo
from coding_agent_playbook.hook_runtime.harness import CLAUDE_EVENT_NAMES
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME, StateStore

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hook_runtime.event import EventName

SESSION_ID = "sess-1"
TOOL_INPUTS: dict[str, dict[str, Any]] = {
    "Bash": {"command": "ls -la"},
    "Edit": {"file_path": "src/app.py", "old_string": "a", "new_string": "b"},
    "Write": {"file_path": "src/new.py", "content": "x = 1\n"},
    "Read": {"file_path": "README.md"},
    "Skill": {"skill": "review"},
}


def hook_record(
    hook_id: str,
    *,
    events: Iterable[str] = ("pre_tool_use",),
    decisions: Iterable[str] = ("deny", "ask", "context", "none"),
    on_error: str = "ask",
    priority: int = 50,
    matcher: Mapping[str, Mapping[str, list[str]]] | None = None,
    handler: Mapping[str, Any] | None = None,
    supports: Iterable[str] = ("claude_code", "opencode"),
    mandatory: bool = False,
    timeout_ms: int = 2000,
    script_sha256: str | None = None,
    source_package: str = "coding_agent_playbook",
) -> dict[str, Any]:
    """One ``guard_config.hooks.<id>`` record; the handler defaults to builtin ``<id>`` snake_cased."""
    event_list = list(events)
    bound = dict(handler or {"kind": "builtin", "name": hook_id.replace("-", "_")})
    bound.setdefault("config", {})
    return {
        "id": hook_id,
        "source_package": source_package,
        "events": event_list,
        "priority": priority,
        "matcher": {e: dict((matcher or {}).get(e, {})) for e in event_list},
        "handlers": {e: dict(bound) for e in event_list},
        "decisions": list(decisions),
        "timeout_ms": timeout_ms,
        "on_error": dict.fromkeys(event_list, on_error),
        "supports": list(supports),
        "mandatory": mandatory,
        "script_sha256": script_sha256,
    }


def canonical(document: Mapping[str, Any]) -> bytes:
    """``guard_config.json``'s canonical bytes (§D.8.1)."""
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return (text + "\n").encode("ascii")


@dataclass
class GuardRepo:
    """A synced fixture repository rooted at ``root`` (a realpath)."""

    root: Path

    @classmethod
    def create(cls, tmp_path: Path) -> GuardRepo:
        root = Path(os.path.realpath(tmp_path)) / "repo"
        (root / ".git").mkdir(parents=True)
        return cls(root)

    @property
    def repo(self) -> RepoInfo:
        git_dir = str(self.root / ".git")
        return RepoInfo(
            worktree_root=str(self.root),
            git_dir=git_dir,
            common_dir=git_dir,
            is_linked_worktree=False,
        )

    @property
    def state_root(self) -> Path:
        return self.root / ".git" / STATE_DIR_NAME

    def store(self) -> StateStore:
        return StateStore(self.state_root)

    def install(self, *records: Mapping[str, Any], **overrides: Any) -> bytes:
        """Write ``guard_config.json`` holding ``records`` and the lockfile entry vouching for it."""
        document: dict[str, Any] = {
            "schema_version": 1,
            "engine_version": "0.1.0a0",
            "hooks": {record["id"]: dict(record) for record in records},
            "logging": {"decisions": True, "audit": False, "audit_mode": ""},
            **overrides,
        }
        data = canonical(document)
        path = self.root / GUARD_CONFIG_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.write_lock(hashlib.sha256(data).hexdigest())
        return data

    def write_lock(self, sha256: str) -> None:
        text = (
            'schema_version = 2\nengine_version = "0.1.0a0"\n'
            f'\n[[entries]]\npath = "{GUARD_CONFIG_REL}"\nsha256 = "{sha256}"\n'
            'bytes = 10\nkind = "runtime"\n'
        )
        (self.root / LOCKFILE_REL).write_text(text, encoding="utf-8")

    def env(self, **extra: str) -> dict[str, str]:
        """The hook process env Claude gives a hook: ``CLAUDE_PROJECT_DIR`` plus ``extra``."""
        return {"CLAUDE_PROJECT_DIR": str(self.root), **extra}

    def payload(self, event: EventName, *, tool: str | None = None, **fields: Any) -> bytes:
        """A Claude-shaped payload for ``event``; ``tool`` adds a canned ``tool_input``."""
        body: dict[str, Any] = {
            "session_id": SESSION_ID,
            "cwd": str(self.root),
            "hook_event_name": CLAUDE_EVENT_NAMES[event],
            "permission_mode": "default",
        }
        if tool is not None:
            body.update(tool_name=tool, tool_input=TOOL_INPUTS[tool], tool_use_id="toolu_1")
        body.update(fields)
        return json.dumps(body).encode("utf-8")

    def decisions(self) -> list[dict[str, Any]]:
        """Every decision-log line written so far, oldest first."""
        lines: list[dict[str, Any]] = []
        for path in sorted(self.state_root.glob("decisions-*.jsonl")):
            lines.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        return lines


def streams() -> tuple[io.StringIO, io.StringIO]:
    """A fresh ``(out, err)`` pair for ``RuntimeDeps``."""
    return io.StringIO(), io.StringIO()
