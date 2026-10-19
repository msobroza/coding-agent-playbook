"""taint-escalation: risky actions ask after the session reads untrusted content (specs/prK-hook-pack.md §E.4).

The opt-in hook's three handlers run through ``playbook-hook simulate`` with
one ``--state`` root, so the per-session flag set by a ``post_tool_use`` marker
(or an out-of-repo read) is what a later ``pre_tool_use`` sees. ``FakeProc``
fails the test on any spawn; ``FakeGit`` is never consulted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName
from tests.hook_runtime.fakes import FakeGit

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "taint-escalation"
PUSH: Final = "git push origin feat"


class Session:
    """One agent session against the fixture repo: shared state, a fake home, no git."""

    def __init__(self, repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
        self.repo = repo
        self.deps = deps
        self.state = tmp_path / "state"
        self.home = tmp_path / "home"
        self.home.mkdir(exist_ok=True)
        self.git = FakeGit()

    def run(
        self,
        tool: str,
        tool_input: dict[str, Any],
        *,
        event: EventName = EventName.PRE_TOOL_USE,
        **fields: Any,
    ) -> SimulateReport:
        payload = self.repo.tool_payload(tool, tool_input, event=event, **fields)
        deps = self.deps(git=self.git, home=str(self.home))
        return self.repo.simulate(payload, deps, event=event, state=self.state)

    def bash(self, command: str, **fields: Any) -> Decision:
        return self.run("Bash", {"command": command}, **fields).trace.combined.decision

    def fetch(self) -> None:
        self.run(
            "WebFetch", {"url": "https://x.io/p", "prompt": "read"}, event=EventName.POST_TOOL_USE
        )

    def start(self, source: str) -> None:
        payload = self.repo.payload(EventName.SESSION_START, source=source)
        deps = self.deps(git=self.git, home=str(self.home))
        self.repo.simulate(payload, deps, event=EventName.SESSION_START, state=self.state)


@pytest.fixture
def session(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> Session:
    pack_repo.install_pack([HOOK_ID])
    return Session(pack_repo, deps, tmp_path)


def test_webfetch_then_push_asks(session: Session) -> None:
    session.fetch()

    report = session.run("Bash", {"command": PUSH})

    assert report.trace.combined.decision is Decision.ASK
    assert report.trace.combined.reason == (
        "This session has read untrusted content (web content); confirm before pushing commits."
    )
    assert session.git.calls == []


def test_untainted_push_passes(session: Session) -> None:
    assert session.bash(PUSH) is Decision.NONE
    assert session.bash("uv add requests") is Decision.NONE


def test_new_session_id_clears(session: Session) -> None:
    session.fetch()

    assert session.bash(PUSH, session_id="sess-2") is Decision.NONE
    assert session.bash(PUSH) is Decision.ASK


def test_session_start_clear_source_clears(session: Session) -> None:
    session.fetch()
    session.start("clear")

    assert session.bash(PUSH) is Decision.NONE


def test_compaction_keeps_taint(session: Session) -> None:
    session.fetch()
    session.start("compact")
    session.start("resume")

    assert session.bash(PUSH) is Decision.ASK


def test_out_of_repo_read_then_uv_add_asks_naming_category(
    session: Session, tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere" / "x.md"
    outside.parent.mkdir()
    outside.write_text("notes\n", encoding="utf-8")

    first = session.run("Read", {"file_path": str(outside)})
    report = session.run("Bash", {"command": "uv add requests"})

    assert first.trace.combined.decision is Decision.NONE  # marking never asks itself
    assert report.trace.combined.decision is Decision.ASK
    assert "(a read outside the repo)" in report.trace.combined.reason
    assert report.trace.combined.reason.endswith("confirm before installing packages.")


def test_in_repo_and_harness_config_reads_do_not_taint(session: Session) -> None:
    skill = session.home / ".claude" / "skills" / "review" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# review\n", encoding="utf-8")
    session.repo.write("README.md", "# demo\n")

    session.run("Read", {"file_path": "README.md"})
    session.run("Read", {"file_path": str(skill)})

    assert session.bash(PUSH) is Decision.NONE


@pytest.mark.parametrize(
    ("tool", "tainted"),
    [
        ("mcp__web__fetch_page", True),
        ("mcp__browser__navigate", True),  # "browse" is in the default pattern
        ("mcp__github__create_issue", False),
        ("mcp__db__query", False),
        ("WebSearch", True),
    ],
)
def test_marker_follows_tool_class_and_mcp_pattern(
    session: Session, tool: str, tainted: bool
) -> None:
    session.run(tool, {"query": "x"}, event=EventName.POST_TOOL_USE)

    assert (session.bash(PUSH) is Decision.ASK) is tainted


@pytest.mark.parametrize(
    ("tool", "tool_input", "expected"),
    [
        ("Bash", {"command": "curl -s https://x.io/a?q=1"}, Decision.ASK),
        ("Bash", {"command": "curl -s http://localhost:8000/health"}, Decision.NONE),
        ("Bash", {"command": "scp a.tar host:/tmp"}, Decision.ASK),
        ("Bash", {"command": "npx left-pad"}, Decision.ASK),
        ("Bash", {"command": "ls -la && uv run pytest"}, Decision.NONE),
        ("Bash", {"command": "echo x > .mcp.json"}, Decision.ASK),
        (
            "Edit",
            {"file_path": ".claude/settings.json", "old_string": "a", "new_string": "b"},
            Decision.ASK,
        ),
        ("Write", {"file_path": "src/app.py", "content": "x = 1\n"}, Decision.NONE),
        ("Read", {"file_path": "~/.bashrc"}, Decision.ASK),
        ("Read", {"file_path": "src/app.py"}, Decision.NONE),
    ],
)
def test_tainted_session_escalates_risky_actions_only(
    session: Session, tool: str, tool_input: dict[str, Any], expected: Decision
) -> None:
    session.fetch()

    assert session.run(tool, tool_input).trace.combined.decision is expected
