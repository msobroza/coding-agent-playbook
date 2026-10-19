"""State, session flags and the ledger under ``<git_dir>/playbook-hooks`` (specs/prK-lifecycle-hooks.md §D.6).

Every row uses a real ``StateStore`` in ``tmp_path``. The state root must be
private (0700 dirs, 0600 files), refuse a planted symlink, bound every lock
wait to 200 ms and fall back to stateless mode instead of failing a tool call.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime.dispatch.event import EventName, RepoInfo, ToolClass
from coding_agent_playbook.hook_runtime.dispatch.paths import find_repo, normalize_path
from coding_agent_playbook.hook_runtime.globs import compile_globs
from coding_agent_playbook.hook_runtime.state.ledger import (
    LEDGER_MAX_LINES,
    Ledger,
    mask_path,
    path_categories,
)
from coding_agent_playbook.hook_runtime.state.session import (
    MAX_ASKED_IDS,
    MAX_DEFERRED_NOTES,
    SessionState,
)
from coding_agent_playbook.hook_runtime.state.store import (
    STATE_DIR_NAME,
    StateStore,
    StateUnavailable,
    iso_utc,
    session_key,
)
from tests.hook_runtime.fakes import FakeClock
from tests.import_probe import probe_env

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.dispatch.proc import SubprocessProc

DAY = 86_400.0


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def _store(tmp_path: Path, **kwargs: object) -> StateStore:
    git_dir = tmp_path / ".git"
    git_dir.mkdir(exist_ok=True)
    return StateStore(git_dir / STATE_DIR_NAME, **kwargs)  # type: ignore[arg-type]


# --- location and permissions ------------------------------------------------------------


@pytest.mark.parametrize("which", ["main", "linked_worktree"])
def test_state_root_equals_git_rev_parse_git_path_playbook_hooks(
    which: str, tmp_path: Path, real_git: Callable[..., str]
) -> None:
    main = tmp_path / "main"
    main.mkdir()
    real_git("init", "-q", cwd=main)
    real_git("commit", "-q", "--allow-empty", "-m", "init", cwd=main)
    real_git("worktree", "add", "-q", str(tmp_path / "feat"), cwd=main)
    top = main if which == "main" else tmp_path / "feat"
    expected = real_git(
        "rev-parse", "--path-format=absolute", "--git-path", STATE_DIR_NAME, cwd=top
    )
    repo = find_repo(str(top))
    assert repo is not None

    store = StateStore.for_repo(repo)

    assert os.path.realpath(store.root) == os.path.realpath(expected)


def test_dirs_are_0700_and_files_0600(tmp_path: Path) -> None:
    store = _store(tmp_path)

    store.update_json("sessions/abc/session.json", lambda doc: doc.update(v=1))
    store.append_jsonl("sessions/abc/ledger.jsonl", {"v": 1})

    root = store.root
    for directory in (root, root / "sessions", root / "sessions" / "abc", root / "locks"):
        assert _mode(directory) == 0o700, directory
    for file in ("sessions/abc/session.json", "sessions/abc/ledger.jsonl", "VERSION"):
        assert _mode(root / file) == 0o600, file
    assert (root / "VERSION").read_text(encoding="utf-8") == "1\n"


def test_permissive_existing_root_is_tightened(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.root.mkdir(mode=0o755)
    store.root.chmod(0o755)

    assert store.usable
    assert _mode(store.root) == 0o700


def test_json_round_trip_and_corrupt_file_reads_empty(tmp_path: Path) -> None:
    store = _store(tmp_path)

    store.write_json("cfg-digest.json", {"sha": "ab"})
    assert store.read_json("cfg-digest.json") == {"sha": "ab"}
    assert store.read_json("absent.json") == {}
    (store.root / "cfg-digest.json").write_text("{not json", encoding="utf-8")
    assert store.read_json("cfg-digest.json") == {}
    (store.root / "cfg-digest.json").write_text("[1]", encoding="utf-8")
    assert store.read_json("cfg-digest.json") == {}


def test_remove_deletes_a_document_and_tolerates_an_absent_one(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_json("sessions/ab/prompt.json", {"slash": "review"})

    store.remove("sessions/ab/prompt.json")
    store.remove("sessions/ab/prompt.json")  # already gone: no error

    assert not (store.root / "sessions" / "ab" / "prompt.json").exists()


def test_update_json_returns_the_change_result_and_persists(tmp_path: Path) -> None:
    store = _store(tmp_path)

    def bump(doc: dict[str, object]) -> int:
        count = int(str(doc.get("n", 0))) + 1
        doc["n"] = count
        return count

    assert [store.update_json("c.json", bump) for _ in range(3)] == [1, 2, 3]
    assert store.read_json("c.json") == {"n": 3}
    assert not list((store.root / "tmp").iterdir())  # temp files never linger


@pytest.mark.parametrize("rel", ["../escape.json", "/abs.json", "a/../../b", "", "a//b"])
def test_paths_outside_the_root_are_refused(tmp_path: Path, rel: str) -> None:
    with pytest.raises(ValueError, match="state path"):
        _store(tmp_path).path(rel)


def test_symlinked_state_root_runs_stateless(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / STATE_DIR_NAME).symlink_to(elsewhere)
    store = StateStore(tmp_path / ".git" / STATE_DIR_NAME)

    assert not store.usable
    assert "symlink" in (store.stateless_reason or "")
    with pytest.raises(StateUnavailable):
        store.update_json("x.json", lambda doc: None)
    with pytest.raises(StateUnavailable):
        store.read_json("x.json")
    session = SessionState(store, "s1")
    assert session.once("k") and session.once("k")  # dedupe is off, never a crash
    assert list(elsewhere.iterdir()) == []


def test_symlinked_subdirectory_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    store.private_dir("")
    (store.root / "sessions").symlink_to(elsewhere)

    with pytest.raises(StateUnavailable, match="symlink"):
        store.write_json("sessions/abc/session.json", {})
    assert list(elsewhere.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership check")
def test_root_owned_by_another_user_runs_stateless(tmp_path: Path) -> None:
    store = _store(tmp_path, uid=os.getuid() + 1)

    assert not store.usable
    assert "owned" in (store.stateless_reason or "")


def test_lock_timeout_runs_that_operation_stateless(tmp_path: Path) -> None:
    store = _store(tmp_path, lock_timeout_s=0.05)
    session = SessionState(store, "s1")
    assert session.once("seen")
    lock = store.lock_path(session.document)
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        with pytest.raises(StateUnavailable, match="busy"):
            store.update_json(session.document, lambda doc: None)
        assert session.once("seen")  # stateless for this one call: shown again
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    assert not session.once("seen")  # the store is used again once the lock frees


def test_two_processes_appending_200_lines_each_give_400_valid_jsonl(
    tmp_path: Path, real_proc: SubprocessProc
) -> None:
    store = _store(tmp_path)
    store.private_dir("")
    code = (
        "import sys\n"
        "from coding_agent_playbook.hook_runtime.state.store import StateStore\n"
        "store = StateStore(sys.argv[1])\n"
        "for i in range(200):\n"
        "    store.append_jsonl('decisions.jsonl', {'w': sys.argv[2], 'i': i, 'pad': 'x' * 900})\n"
    )

    def writer(name: str) -> int:
        argv = [sys.executable, "-c", code, str(store.root), name]
        return real_proc.run(argv, timeout=120, env=probe_env()).returncode

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(writer, ["a", "b"]))

    assert codes == [0, 0]
    lines = (store.root / "decisions.jsonl").read_bytes().splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == 400
    assert sorted((r["w"], r["i"]) for r in records) == sorted(
        (w, i) for w in "ab" for i in range(200)
    )


# --- TTL sweep -----------------------------------------------------------------------------


def _age(path: Path, seconds_ago: float, now: float) -> None:
    os.utime(path, (now - seconds_ago, now - seconds_ago))


def test_ttl_sweep_removes_only_expired_entries(tmp_path: Path) -> None:
    clock = FakeClock()
    now = clock.time()
    store = _store(tmp_path, clock=clock)
    for name, age in (("old", 8 * DAY), ("fresh", 1 * DAY)):
        store.write_json(f"sessions/{name}/session.json", {})
        _age(store.root / "sessions" / name / "session.json", age, now)
        _age(store.root / "sessions" / name, age, now)
    store.private_dir("tmp")
    for name, age in (("old.tmp", 2 * DAY), ("new.tmp", 60.0)):
        (store.root / "tmp" / name).write_text("", encoding="utf-8")
        _age(store.root / "tmp" / name, age, now)
    for tree, age in (("aaa", 8 * DAY), ("bbb", 8 * DAY), ("ccc", 1 * DAY)):
        store.write_json(f"stop/lint-baseline-{tree}.json", {})
        _age(store.root / "stop" / f"lint-baseline-{tree}.json", age, now)
    for month in ("2026-01", "2026-04", "2026-10"):
        store.append_jsonl(f"decisions-{month}.jsonl", {"v": 1})
    store.append_jsonl("decisions-2026-02.1.jsonl", {"v": 1})

    report = store.sweep(ttl_days=7, retain_months=6, head_tree="bbb")

    assert report.complete
    assert sorted(p.name for p in (store.root / "sessions").iterdir()) == ["fresh"]
    assert sorted(p.name for p in (store.root / "tmp").iterdir()) == ["new.tmp"]
    assert sorted(p.name for p in (store.root / "stop").iterdir()) == [
        "lint-baseline-bbb.json",
        "lint-baseline-ccc.json",
    ]
    logs = sorted(p.name for p in store.root.glob("decisions-*.jsonl"))
    assert logs == ["decisions-2026-04.jsonl", "decisions-2026-10.jsonl"]
    assert store.read_json("sweep.json")["last_complete"] == now


def test_ttl_sweep_is_bounded_to_500_entries_and_resumes(tmp_path: Path) -> None:
    clock = FakeClock()
    now = clock.time()
    store = _store(tmp_path, clock=clock)
    for index in range(600):
        directory = store.private_dir(f"sessions/s{index:04d}")
        _age(directory, 30 * DAY, now)

    first = store.sweep(ttl_days=7)
    second = store.sweep(ttl_days=7)

    assert (first.examined, first.removed, first.complete) == (500, 500, False)
    assert (second.removed, second.complete) == (100, True)
    assert list((store.root / "sessions").iterdir()) == []


def test_ttl_sweep_stops_at_its_time_budget(tmp_path: Path) -> None:
    clock = FakeClock()
    store = _store(tmp_path, clock=clock)
    for index in range(3):
        _age(store.private_dir(f"sessions/s{index}"), 30 * DAY, clock.time())

    class TickingClock(FakeClock):
        def monotonic(self) -> float:
            self.mono += 0.015
            return self.mono

    report = StateStore(store.root, clock=TickingClock(now=clock.now)).sweep(ttl_days=7)

    assert not report.complete
    assert report.examined < 3


def test_sweep_is_due_once_a_day(tmp_path: Path) -> None:
    clock = FakeClock()
    store = _store(tmp_path, clock=clock)

    assert store.sweep_due()
    store.sweep(ttl_days=7)
    assert not store.sweep_due()
    clock.advance(DAY + 1)
    assert store.sweep_due()


# --- session state ---------------------------------------------------------------------------


def test_session_dir_is_a_digest_of_the_session_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = SessionState(store, "../../etc")

    session.set_flag("tainted")

    key = hashlib.sha256(b"../../etc").hexdigest()[:16]
    assert session_key("../../etc") == key
    assert (store.root / "sessions" / key / "session.json").is_file()


def test_session_once_flags_asked_cap_64_notes_cap_5(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = SessionState(store, "s1")
    other = SessionState(store, "s2")

    assert session.once("ctx:a") and not session.once("ctx:a")
    assert other.once("ctx:a")  # per session
    assert not session.flag("tainted")
    session.set_flag("tainted")
    assert session.flag("tainted") and not other.flag("tainted")
    for index in range(MAX_ASKED_IDS + 6):
        session.mark_asked(f"toolu_{index}")
    assert not session.was_asked("toolu_0")  # the oldest ids fall out
    assert session.was_asked(f"toolu_{MAX_ASKED_IDS + 5}")
    assert len(store.read_json(session.document)["asked"]) == MAX_ASKED_IDS
    for index in range(MAX_DEFERRED_NOTES + 2):
        session.push_note(f"note {index}")
    session.push_note("note 6")  # a duplicate is not queued twice
    assert session.drain_notes() == [f"note {i}" for i in range(2, MAX_DEFERRED_NOTES + 2)]
    assert session.drain_notes() == []


def test_stateless_session_keeps_flags_and_notes_in_memory(tmp_path: Path) -> None:
    store = _store(tmp_path, uid=os.getuid() + 1)
    session = SessionState(store, "s1")

    session.set_flag("tainted")
    session.mark_asked("toolu_1")
    session.push_note("hello")

    assert session.flag("tainted")
    assert session.was_asked("toolu_1")
    assert session.drain_notes() == ["hello"]
    assert session.once("k") and session.once("k")


# --- ledger ----------------------------------------------------------------------------------


def _repo(root: Path) -> RepoInfo:
    return RepoInfo(
        worktree_root=str(root),
        git_dir=str(root / ".git"),
        common_dir=str(root / ".git"),
        is_linked_worktree=False,
    )


def _ledger(tmp_path: Path, store: StateStore) -> Ledger:
    return Ledger(
        store,
        "s1",
        path_classes={
            "py": compile_globs(["*.py"], platform="linux"),
            "generated": compile_globs(["build/"], platform="linux"),
        },
        secret_paths=compile_globs([".env*", "*.pem"], platform="linux"),
        now=FakeClock().time,
        platform="linux",
    )


def test_ledger_masks_outside_and_secret_paths_and_caps_2000_lines(tmp_path: Path) -> None:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    store = _store(root)
    ledger = _ledger(root, store)
    repo = _repo(root)

    def norm(raw: str) -> object:
        return normalize_path(raw, base=str(root), repo=repo, home="/home/dev", platform="linux")

    ledger.record_touch(
        event=EventName.POST_TOOL_USE,
        tool_class=ToolClass.EDIT,
        tool="Edit",
        paths=[norm("src/x.py"), norm("/etc/passwd"), norm("deploy/.env.prod")],  # type: ignore[list-item]
    )
    ledger.record_touch(
        event=EventName.POST_TOOL_USE,
        tool_class=ToolClass.SHELL,
        tool="Bash",
        writes=[norm("build/out.txt")],  # type: ignore[list-item]
    )
    ledger.record_verify(
        event=EventName.POST_TOOL_USE_FAILURE, verify="tests", ok=False, exit_code=1
    )

    first, second, third = ledger.read()
    assert first == {
        "v": 1,
        "ts": iso_utc(FakeClock().time()),
        "ev": "post_tool_use",
        "tc": "edit",
        "tool": "Edit",
        "paths": ["src/x.py", "<outside>", "<secret-path>"],
        "cats": ["py", "secret"],
    }
    assert (second["writes"], second["cats"]) == (["build/out.txt"], ["generated"])
    assert {k: third[k] for k in ("ev", "tc", "verify", "ok", "exit")} == {
        "ev": "post_tool_use_failure",
        "tc": "shell",
        "verify": "tests",
        "ok": False,
        "exit": 1,
    }
    text = ledger.path.read_text(encoding="utf-8")
    assert str(root) not in text and ".env.prod" not in text and "passwd" not in text

    for index in range(LEDGER_MAX_LINES):
        ledger.record_touch(
            event=EventName.POST_TOOL_USE,
            tool_class=ToolClass.EDIT,
            tool="Edit",
            paths=[norm(f"src/m{index % 7}.py")],  # type: ignore[list-item]
        )
    ledger.record_verify(event=EventName.POST_TOOL_USE, verify="lint", ok=True)

    records = ledger.read()
    assert len(records) <= LEDGER_MAX_LINES
    summary = records[0]
    assert summary["ev"] == "summary"
    assert set(summary["paths"]) >= {"src/x.py", "<outside>", "<secret-path>", "src/m6.py"}
    assert summary["writes"] == ["build/out.txt"]
    assert records[-1]["verify"] == "lint"


def test_ledger_shrinks_a_record_that_would_exceed_one_line(tmp_path: Path) -> None:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    store = _store(root)
    ledger = _ledger(root, store)
    repo = _repo(root)
    paths = [
        normalize_path(
            f"src/{'d' * 80}/f{i}.py", base=str(root), repo=repo, home=None, platform="linux"
        )
        for i in range(200)
    ]

    ledger.record_touch(
        event=EventName.POST_TOOL_USE, tool_class=ToolClass.EDIT, tool="Edit", paths=paths
    )

    (record,) = ledger.read()
    assert record["truncated"] is True
    assert 0 < len(record["paths"]) < 200


def test_mask_and_categories_on_a_case_folding_platform(tmp_path: Path) -> None:
    root = Path(os.path.realpath(tmp_path))
    repo = _repo(root)
    secret = compile_globs([".env*"], platform="darwin")
    classes = {"py": compile_globs(["*.py"], platform="darwin")}
    path = normalize_path("SRC/.ENV.local", base=str(root), repo=repo, home=None, platform="darwin")
    code = normalize_path("A.PY", base=str(root), repo=repo, home=None, platform="darwin")

    assert mask_path(path, secret, platform="darwin") == "<secret-path>"
    assert path_categories(path, classes, secret, platform="darwin") == ("secret",)
    assert mask_path(code, secret, platform="darwin") == "A.PY"
    assert path_categories(code, classes, secret, platform="darwin") == ("py",)


def test_ledger_in_stateless_mode_records_nothing_and_reads_empty(tmp_path: Path) -> None:
    store = _store(tmp_path, uid=os.getuid() + 1)
    ledger = _ledger(tmp_path, store)

    assert not ledger.record_verify(event=EventName.POST_TOOL_USE, verify="lint", ok=True)
    assert ledger.read() == []
