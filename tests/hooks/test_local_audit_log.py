"""local-audit-log: structure-only activity lines and the async dispatch (specs/prK-hook-pack.md §E.5).

The opt-in hook runs through ``playbook-hook simulate`` with one ``--state``
root, so each test reads the ``audit-YYYY-MM.jsonl`` line the dispatch wrote.
``post_tool_use`` is async-routed (OQ-19): only ``--async`` runs it, with
empty stdout, and the synchronous dispatch skips it. ``FakeProc`` fails the
test on any spawn; no network, no real git.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.handlers._activity_record import (
    command_structure,
    fitted,
    flag_name,
)
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME
from coding_agent_playbook.security.audit import MAX_LINE_BYTES, encode_jsonl_line, verify_chain

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hooks.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

HOOK_ID: Final = "local-audit-log"
LEAKY: Final = "mysql -pS3cret db"
#: A token the secret rules flag (``security.secrets.scan_text``'s own example).
AWS_KEY: Final = "AKIA" + "Z7Q2" * 4
#: A valid IBAN (ISO 13616 check digits 76) and a Luhn-valid Visa, neither a test value.
IBAN: Final = "FR7630006000011234567890189"
CARD: Final = "4539148803436467"


class Audit:
    """One session against a repo with local-audit-log on: shared state, the audit lines."""

    def __init__(self, repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
        self.repo = repo
        self.deps = deps
        self.state = tmp_path / "state"

    def run(
        self, event: EventName, payload: bytes, *, asynchronous: bool = False
    ) -> SimulateReport:
        return self.repo.simulate(
            payload, self.deps(), event=event, state=self.state, asynchronous=asynchronous
        )

    def tool(
        self,
        tool: str,
        tool_input: dict[str, Any],
        *,
        event: EventName = EventName.POST_TOOL_USE,
        asynchronous: bool = True,
        **fields: Any,
    ) -> SimulateReport:
        payload = self.repo.tool_payload(tool, tool_input, event=event, **fields)
        return self.run(event, payload, asynchronous=asynchronous)

    @property
    def log(self) -> Path:
        return self.state / STATE_DIR_NAME / "audit-2026-10.jsonl"

    def lines(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="ascii").splitlines()]


def _audit(pack_repo: PackRepo, deps: Deps, tmp_path: Path, **config: Any) -> Audit:
    pack_repo.install_pack([HOOK_ID], per_hook={HOOK_ID: config} if config else None)
    return Audit(pack_repo, deps, tmp_path)


@pytest.fixture
def audit(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> Audit:
    return _audit(pack_repo, deps, tmp_path)


def test_mysql_password_flag_records_argv0_and_flag_name_not_value(audit: Audit) -> None:
    audit.tool("Bash", {"command": LEAKY})

    (line,) = audit.lines()
    assert line["commands"] == [{"argv0": "mysql", "sub": None, "flags": ["-p"]}]
    assert (line["event"], line["tool_name"], line["tool_class"]) == (
        "post_tool_use",
        "Bash",
        "shell",
    )
    assert (line["ok"], line["duration_ms"]) == (True, None)
    raw = audit.log.read_text(encoding="ascii")
    assert "S3cret" not in raw
    assert '"db"' not in raw  # a positional argument is a value too


def test_git_subcommand_and_long_flag_names_only(audit: Audit) -> None:
    audit.tool("Bash", {"command": "git push --repo=https://u:pw@h.example/r.git origin main"})

    (line,) = audit.lines()
    assert line["commands"] == [{"argv0": "git", "sub": "push", "flags": ["--repo"]}]
    assert "pw@" not in audit.log.read_text(encoding="ascii")


def test_secret_path_recorded_as_category_only(audit: Audit) -> None:
    audit.repo.write(".env", "TOKEN=x\n")
    audit.repo.write("src/app.py", "x = 1\n")

    audit.tool("Read", {"file_path": str(audit.repo.root / ".env")})
    audit.tool("Read", {"file_path": str(audit.repo.root / "src" / "app.py")})

    paths = [line["paths"] for line in audit.lines()]
    assert paths == [["<secret-path>"], ["src/app.py"]]
    assert str(audit.repo.root) not in audit.log.read_text(encoding="ascii")


def test_prompt_recorded_as_length_sha256_and_counts_only(audit: Audit) -> None:
    prompt = f"deploy with key {AWS_KEY} please"
    payload = audit.repo.payload(EventName.USER_PROMPT_SUBMIT, prompt=prompt)

    report = audit.run(EventName.USER_PROMPT_SUBMIT, payload)

    (line,) = audit.lines()
    assert line["prompt"] == {
        "length": len(prompt),
        "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "secrets": {"aws-access-key-id": 1},
    }
    raw = audit.log.read_text(encoding="ascii")
    assert AWS_KEY not in raw and "deploy" not in raw
    assert report.trace.wire.stdout == ""


def test_prompt_pii_category_counts_only_when_enabled(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    """PII counts join the prompt record only when an overlay lists detectors in ``pii``."""
    prompt = f"wire {IBAN} from card {CARD} (test card 4111 1111 1111 1111)"
    payload = pack_repo.payload(EventName.USER_PROMPT_SUBMIT, prompt=prompt)
    off = _audit(pack_repo, deps, tmp_path)
    off.run(EventName.USER_PROMPT_SUBMIT, payload)

    on = _audit(pack_repo, deps, tmp_path / "on", pii=["iban", "card_pan"])
    on.run(EventName.USER_PROMPT_SUBMIT, payload)

    (plain,) = off.lines()
    (counted,) = on.lines()
    assert "pii" not in plain["prompt"]
    assert counted["prompt"]["pii"] == {"card_pan": 1, "iban": 1}
    raw = on.log.read_text(encoding="ascii")
    assert IBAN[4:] not in raw and CARD not in raw and "wire" not in raw


def test_async_dispatch_writes_empty_stdout(audit: Audit) -> None:
    report = audit.tool("Read", {"file_path": "README.md"})

    assert report.trace.wire.stdout == ""
    assert report.trace.wire.exit_code == 0
    assert [done.selected.record.id for done in report.trace.ran] == [HOOK_ID]
    assert len(audit.lines()) == 1


def test_sync_post_tool_use_skips_async_routed_handler(audit: Audit) -> None:
    report = audit.tool("Bash", {"command": "ls"}, asynchronous=False)

    assert report.trace.ran == ()
    assert audit.lines() == []


def test_async_flag_on_another_event_is_a_contract_fault_not_an_audit(audit: Audit) -> None:
    report = audit.tool("Bash", {"command": "ls"}, event=EventName.PRE_TOOL_USE)

    assert report.trace.ran == ()
    assert report.trace.combined.decision.value == "ask"  # a fault on pre_tool_use asks
    assert audit.lines() == []


def test_post_tool_use_failure_records_exit_status(audit: Audit) -> None:
    payload = audit.repo.payload(
        EventName.POST_TOOL_USE_FAILURE,
        tool_name="Bash",
        tool_input={"command": "pytest -x"},
        tool_use_id="toolu_f",
        error="Exit code 2\nboom",
    )

    report = audit.run(EventName.POST_TOOL_USE_FAILURE, payload)

    (line,) = audit.lines()
    assert (line["ok"], line["exit_code"], line["interrupted"]) == (False, 2, False)
    assert line["commands"] == [{"argv0": "pytest", "sub": None, "flags": ["-x"]}]
    assert "boom" not in audit.log.read_text(encoding="ascii")
    assert report.trace.wire.stdout == ""


def test_session_boundaries_are_recorded(audit: Audit) -> None:
    start = audit.repo.payload(EventName.SESSION_START, source="resume")
    end = audit.repo.payload(EventName.SESSION_END, reason="exit")

    audit.run(EventName.SESSION_START, start)
    audit.run(EventName.SESSION_END, end)

    assert [(line["event"], line.get("source")) for line in audit.lines()] == [
        ("session_start", "resume"),
        ("session_end", None),
    ]


def test_full_commands_text_is_redacted(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    audit = _audit(pack_repo, deps, tmp_path, full_commands=True)

    audit.tool("Bash", {"command": f"{LEAKY} && curl -u bob:hunter2 https://x.io/{AWS_KEY}"})

    (line,) = audit.lines()
    text = line["command_text"]
    assert text.startswith("mysql -p<redacted> db ; curl -u <redacted> https://x.io/")
    for leaked in ("S3cret", "hunter2", AWS_KEY):
        assert leaked not in audit.log.read_text(encoding="ascii")


def test_chain_config_links_lines(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    audit = _audit(pack_repo, deps, tmp_path, chain=True)

    for name in ("a.md", "b.md", "c.md"):
        audit.tool("Read", {"file_path": name})

    assert [line["prev"] is None for line in audit.lines()] == [True, False, False]
    assert verify_chain(audit.log) is None


def test_session_start_prunes_month_files_past_retention(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    audit = _audit(pack_repo, deps, tmp_path, retain_days=30)
    old = audit.state / STATE_DIR_NAME / "audit-2026-08.jsonl"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"{}\n")

    audit.run(
        EventName.SESSION_START, audit.repo.payload(EventName.SESSION_START, source="startup")
    )

    assert not old.exists()
    assert len(audit.lines()) == 1


def test_oversized_record_is_trimmed_to_one_atomic_line() -> None:
    """A line stays one O_APPEND write even with the chain's ``prev`` (``security.audit``)."""
    flags = [f"--flag-{n:02d}-{'x' * 28}" for n in range(8)]
    record = {
        "v": 1,
        "ts": "2026-10-14T10:30:00.123Z",
        "event": "post_tool_use",
        "commands": [{"argv0": "tool", "sub": None, "flags": flags} for _ in range(8)],
        "paths": [f"src/{'deep/' * 40}{n}.py" for n in range(8)],
        "command_text": "y" * 1024,
    }

    trimmed = fitted(record)

    assert "command_text" not in trimmed
    assert 0 < len(trimmed["paths"]) < 8
    assert len(encode_jsonl_line({**trimmed, "prev": "0" * 64})) <= MAX_LINE_BYTES


@pytest.mark.parametrize(
    ("arg", "name"),
    [("-pS3cret", "-p"), ("--password=x", "--password"), ("-", None), ("--", None), ("db", None)],
)
def test_flag_name_keeps_names_never_values(arg: str, name: str | None) -> None:
    assert flag_name(arg) == name
    assert command_structure(["/usr/bin/mysql", arg, "db"])["argv0"] == "mysql"
