"""Tests for the append-only JSONL writers (specs/prK-lifecycle-hooks.md §D.6.1, §D.6.2, P-D4).

``append_jsonl`` is the one generic writer (decision log, local audit log, the
SPEC §17.4 sync audit line); ``append_decision`` is the typed decision-log
wrapper. Every test writes under ``tmp_path``; the concurrency test runs two
real writer processes against one log.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from typing import TYPE_CHECKING, cast

import pytest

from coding_agent_playbook.security import audit
from coding_agent_playbook.security.audit import (
    DECISION_RECORD_KEYS,
    MAX_LINE_BYTES,
    GuardDecisionRecord,
    append_decision,
    append_jsonl,
    decision_log_path,
    encode_jsonl_line,
    rotated_log_path,
    rotation_lock_path,
)
from tests.import_probe import PROBE_TIMEOUT_S, new_modules_after

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes and flock")

#: §D.6.2's example line, keys sorted, compact separators, trailing newline.
_SPEC_EXAMPLE_LINE = (
    '{"canary":false,"decision":"deny","degraded":false,"effective":"deny","escape":null,'
    '"event":"pre_tool_use","harness":"claude_code","hook_id":"destructive-command-guard",'
    '"latency_ms":41,"rule_id":"rm_root","session_id":"abc123","tool_class":"shell",'
    '"tool_name":"Bash","ts":"2026-10-14T10:30:00.123Z","unattended":false,"v":1}\n'
)

#: §D.6.2's field list, verbatim.
_SPEC_KEYS = {
    "v",
    "ts",
    "harness",
    "session_id",
    "event",
    "hook_id",
    "rule_id",
    "decision",
    "effective",
    "tool_name",
    "tool_class",
    "unattended",
    "degraded",
    "escape",
    "canary",
    "latency_ms",
}


def _record(*, ts: str = "2026-10-14T10:30:00.123Z", latency_ms: int = 41) -> GuardDecisionRecord:
    return {
        "v": 1,
        "ts": ts,
        "harness": "claude_code",
        "session_id": "abc123",
        "event": "pre_tool_use",
        "hook_id": "destructive-command-guard",
        "rule_id": "rm_root",
        "decision": "deny",
        "effective": "deny",
        "tool_name": "Bash",
        "tool_class": "shell",
        "unattended": False,
        "degraded": False,
        "escape": None,
        "canary": False,
        "latency_ms": latency_ms,
    }


def _padded(size: int) -> dict[str, object]:
    """A record whose encoded line, newline included, is exactly ``size`` bytes."""
    overhead = len(encode_jsonl_line({"pad": ""}))
    return {"pad": "x" * (size - overhead)}


@pytest.fixture
def default_umask() -> Iterator[None]:
    """Pin the umask to the common 022 so mode assertions do not depend on the shell."""
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


# --------------------------------------------------------------------------- #
# append_decision: the typed decision-log wrapper
# --------------------------------------------------------------------------- #


def test_append_decision_writes_one_sorted_compact_line_in_month_file(tmp_path: Path) -> None:
    append_decision(tmp_path, _record())

    assert sorted(path.name for path in tmp_path.iterdir()) == ["decisions-2026-10.jsonl"]
    assert (tmp_path / "decisions-2026-10.jsonl").read_text(encoding="ascii") == _SPEC_EXAMPLE_LINE


def test_append_decision_takes_the_month_from_ts_not_the_clock(tmp_path: Path) -> None:
    append_decision(tmp_path, _record(ts="2019-03-31T23:59:59Z"))
    assert (tmp_path / "decisions-2019-03.jsonl").is_file()


def test_append_decision_appends_lines_in_order(tmp_path: Path) -> None:
    append_decision(tmp_path, _record(latency_ms=1))
    append_decision(tmp_path, _record(latency_ms=2))

    lines = (tmp_path / "decisions-2026-10.jsonl").read_text(encoding="ascii").splitlines()
    assert [json.loads(line)["latency_ms"] for line in lines] == [1, 2]


@pytest.mark.parametrize(
    "ts",
    [
        "",
        "2026-13-01T00:00:00Z",
        "26-10-14T00:00:00Z",
        "2026/10/14",
        "\uff12\uff10\uff12\uff16-10-14T00:00:00Z",  # fullwidth digits never name a file
    ],
)
def test_decision_log_path_rejects_a_malformed_ts_naming_it(tmp_path: Path, ts: str) -> None:
    with pytest.raises(ValueError, match=repr(ts)):
        decision_log_path(tmp_path, ts)


def test_append_decision_rejects_content_keys_naming_them(tmp_path: Path) -> None:
    leaky = cast("GuardDecisionRecord", {**_record(), "command": "mysql -pS3cret"})

    with pytest.raises(ValueError, match="'command'"):
        append_decision(tmp_path, leaky)
    assert list(tmp_path.iterdir()) == []


def test_append_decision_rejects_missing_keys_naming_them(tmp_path: Path) -> None:
    partial = dict(_record())
    del partial["canary"]

    with pytest.raises(ValueError, match="'canary'"):
        append_decision(tmp_path, cast("GuardDecisionRecord", partial))


def test_decision_record_has_no_content_fields() -> None:
    # D-10: identifiers and flags only; never command, path, prompt, reason or env text.
    assert set(GuardDecisionRecord.__required_keys__) == _SPEC_KEYS
    assert DECISION_RECORD_KEYS == _SPEC_KEYS
    forbidden = {"command", "cmd", "path", "paths", "prompt", "reason", "context", "env"}
    assert not forbidden & _SPEC_KEYS


# --------------------------------------------------------------------------- #
# append_jsonl: the generic writer
# --------------------------------------------------------------------------- #


@_POSIX_ONLY
@pytest.mark.usefixtures("default_umask")
def test_append_jsonl_creates_file_mode_0600(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    append_jsonl(log, {"a": 1})
    assert log.stat().st_mode & 0o777 == 0o600


@_POSIX_ONLY
def test_append_jsonl_refuses_symlinked_log(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.txt"
    target.write_text("original\n", encoding="utf-8")
    log = tmp_path / "decisions-2026-10.jsonl"
    log.symlink_to(target)

    with pytest.raises(OSError):
        append_jsonl(log, {"a": 1})
    assert target.read_text(encoding="utf-8") == "original\n"


def test_append_jsonl_rejects_line_over_4096_bytes_naming_size(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    with pytest.raises(ValueError, match="4097 bytes"):
        append_jsonl(log, _padded(MAX_LINE_BYTES + 1))
    assert not log.exists()


def test_append_jsonl_accepts_a_line_of_exactly_4096_bytes(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    append_jsonl(log, _padded(MAX_LINE_BYTES))
    assert log.stat().st_size == MAX_LINE_BYTES


def test_append_jsonl_rejects_nan_which_is_not_json(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        append_jsonl(tmp_path / "audit.jsonl", {"x": float("nan")})


def test_encode_jsonl_line_escapes_newlines_and_non_ascii() -> None:
    line = encode_jsonl_line({"text": "a\nb", "arrow": "ask→deny"})
    assert line == b'{"arrow":"ask\\u2192deny","text":"a\\nb"}\n'


def test_append_jsonl_rotates_at_size_cap(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    line_size = len(encode_jsonl_line({"n": 0}))
    for n in range(6):
        append_jsonl(log, {"n": n}, rotate_bytes=2 * line_size)

    def numbers(path: Path) -> list[int]:
        return [json.loads(line)["n"] for line in path.read_text(encoding="ascii").splitlines()]

    # A file reaching the cap is rotated before the next line, so each rotated
    # copy holds exactly rotate_bytes.
    assert numbers(rotated_log_path(log, 1)) == [0, 1]
    assert numbers(rotated_log_path(log, 2)) == [2, 3]
    assert numbers(log) == [4, 5]
    assert rotated_log_path(log, 1).name == "audit.1.jsonl"


@_POSIX_ONLY
@pytest.mark.usefixtures("default_umask")
def test_rotation_lock_is_a_0600_sidecar(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    log.write_bytes(b"{}\n")
    append_jsonl(log, {"n": 1}, rotate_bytes=1)

    lock = rotation_lock_path(log)
    assert lock.name == "audit.jsonl.lock"
    assert lock.stat().st_mode & 0o777 == 0o600


@_POSIX_ONLY
def test_append_jsonl_skips_rotation_while_the_lock_is_busy(tmp_path: Path) -> None:
    import fcntl

    log = tmp_path / "audit.jsonl"
    log.write_bytes(b"{}\n")
    holder = os.open(rotation_lock_path(log), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        started = time.monotonic()
        append_jsonl(log, {"n": 1}, rotate_bytes=1, lock_timeout_s=0.05)
        elapsed = time.monotonic() - started
    finally:
        os.close(holder)

    assert elapsed < 1.0
    assert not rotated_log_path(log, 1).exists()
    assert log.read_bytes() == b'{}\n{"n":1}\n'


def test_append_jsonl_still_appends_when_rotation_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows refuses to rename a file another process holds open; the line must still land.
    def refuse_rename(src: object, dst: object) -> None:
        raise PermissionError(f"cannot rename {src} -> {dst}")

    log = tmp_path / "audit.jsonl"
    log.write_bytes(b"{}\n")
    monkeypatch.setattr(os, "rename", refuse_rename)

    append_jsonl(log, {"n": 1}, rotate_bytes=1)

    assert log.read_bytes() == b'{}\n{"n":1}\n'


def test_append_jsonl_keeps_appending_when_every_rotation_name_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit, "_MAX_ROTATIONS", 1)
    log = tmp_path / "audit.jsonl"
    log.write_bytes(b"{}\n")
    rotated_log_path(log, 1).write_bytes(b"old\n")

    append_jsonl(log, {"n": 1}, rotate_bytes=1)

    assert log.read_bytes() == b'{}\n{"n":1}\n'
    assert rotated_log_path(log, 1).read_bytes() == b"old\n"


def test_append_jsonl_reports_a_short_write_naming_the_sizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "audit.jsonl"
    # Patched only around the call: pytest itself writes through os.write.
    with monkeypatch.context() as patch:
        patch.setattr(os, "write", lambda _fd, data: len(data) - 1)
        with pytest.raises(OSError, match=r"short write .* 7 of 8 bytes"):
            append_jsonl(log, {"n": 1})


_WRITER = textwrap.dedent(
    """\
    import pathlib, sys, time
    from coding_agent_playbook.security.audit import append_jsonl

    log, go, writer = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
    deadline = time.monotonic() + 30
    while not go.exists() and time.monotonic() < deadline:
        time.sleep(0.001)
    for seq in range(int(sys.argv[4])):
        append_jsonl(log, {"writer": writer, "seq": seq, "pad": "x" * 40}, rotate_bytes=2048)
    """
)


def test_two_concurrent_writer_processes_produce_valid_jsonl(tmp_path: Path) -> None:
    log, go, per_writer = tmp_path / "events.jsonl", tmp_path / "go", 300
    writers = [
        subprocess.Popen(
            [sys.executable, "-c", _WRITER, str(log), str(go), name, str(per_writer)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for name in ("a", "b")
    ]
    go.touch()  # both writers start appending at once, so rotations contend
    for writer in writers:
        _, stderr = writer.communicate(timeout=PROBE_TIMEOUT_S)
        assert writer.returncode == 0, stderr

    logs = sorted(tmp_path.glob("events*.jsonl"))
    records = [json.loads(line) for path in logs for line in path.read_text("ascii").splitlines()]
    seen = sorted((record["writer"], record["seq"]) for record in records)
    assert seen == sorted((name, seq) for name in ("a", "b") for seq in range(per_writer))
    assert len(logs) > 1


def test_audit_module_imports_only_the_stdlib() -> None:
    loaded = new_modules_after("import coding_agent_playbook.security.audit")
    foreign = [
        name
        for name in loaded
        if not name.startswith("coding_agent_playbook.security")
        and name.split(".")[0] not in sys.stdlib_module_names
    ]
    assert foreign == []
    assert "coding_agent_playbook.security.audit" in loaded
