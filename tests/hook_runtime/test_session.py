"""``SessionState.debounce`` and its flags (specs/prK-hook-pack.md §E.0.4, §E.4).

The stamp is the store clock's wall time, so a ``FakeClock`` drives it and a
second hook process (a new ``SessionState`` on the same store) sees it too.
Flags (taint-escalation's ``taint:*``) last for the session; only
``clear_flag`` drops one, stored or kept in memory while stateless.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.session import MAX_DEBOUNCE_KEYS, SessionState
from coding_agent_playbook.hook_runtime.state import StateStore
from tests.hook_runtime.fakes import FakeClock

if TYPE_CHECKING:
    from pathlib import Path


def _session(tmp_path: Path, clock: FakeClock, session_id: str = "s-1") -> SessionState:
    return SessionState(StateStore(tmp_path / "playbook-hooks", clock=clock), session_id)


def test_debounce_suppresses_within_window_and_reopens_after(tmp_path: Path) -> None:
    clock = FakeClock()
    session = _session(tmp_path, clock)

    first = session.debounce("validate", 2.0)
    clock.advance(1.5)
    within = _session(tmp_path, clock).debounce("validate", 2.0)  # a later hook process
    other_key = session.debounce("eval-lint", 2.0)
    clock.advance(0.6)
    after = session.debounce("validate", 2.0)

    assert (first, within, other_key, after) == (True, False, True, True)


def test_debounce_is_per_session_and_open_when_stateless(tmp_path: Path) -> None:
    clock = FakeClock()
    _session(tmp_path, clock, "s-1").debounce("validate", 2.0)
    blocked = tmp_path / "file"
    blocked.write_text("not a directory\n", encoding="utf-8")
    stateless = SessionState(StateStore(blocked, clock=clock), "s-1")

    assert _session(tmp_path, clock, "s-2").debounce("validate", 2.0) is True
    assert stateless.debounce("validate", 2.0) is True
    assert stateless.debounce("validate", 2.0) is True  # dedupe off: nothing silently dropped


def test_debounce_keeps_the_newest_keys_and_reopens_when_the_clock_goes_back(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    session = _session(tmp_path, clock)
    for index in range(MAX_DEBOUNCE_KEYS + 1):
        session.debounce(f"k{index}", 2.0)

    stored = session_document(tmp_path, session)["debounce"]
    clock.now -= 10

    assert len(stored) == MAX_DEBOUNCE_KEYS and "k0" not in stored
    assert session.debounce(f"k{MAX_DEBOUNCE_KEYS}", 2.0) is True


def test_flags_persist_across_processes_until_cleared(tmp_path: Path) -> None:
    clock = FakeClock()
    _session(tmp_path, clock).set_flag("taint:web")
    _session(tmp_path, clock).set_flag("taint:read")

    later = _session(tmp_path, clock)  # a later hook process
    before = (later.flags(), later.flag("taint:web"), _session(tmp_path, clock, "s-2").flags())
    later.clear_flag("taint:web")
    later.clear_flag("taint:read")

    assert before == (("taint:web", "taint:read"), True, ())
    assert _session(tmp_path, clock).flags() == ()
    assert "flags" not in session_document(tmp_path, later)


def test_clear_flag_also_clears_the_in_memory_flag_when_stateless(tmp_path: Path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("not a directory\n", encoding="utf-8")
    stateless = SessionState(StateStore(blocked, clock=FakeClock()), "s-1")
    stateless.set_flag("taint:web")
    kept = stateless.flags()

    stateless.clear_flag("taint:web")

    assert (kept, stateless.flags()) == (("taint:web",), ())


def session_document(tmp_path: Path, session: SessionState) -> dict[str, Any]:
    """The stored ``session.json`` of ``session``."""
    return StateStore(tmp_path / "playbook-hooks").read_json(session.document)
