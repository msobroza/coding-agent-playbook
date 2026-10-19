"""The decision model: combination, caps, ask degradation and the policy tables (§D.3, §D.4).

``combine`` is pure: the session-scoped dedupe arrives as an injected ``once``
callable (``FakeOnce`` here) and the ask policy as a plain value, so every rule
of §D.3.3 is checked without state, git or a config file. The runtime may not
import ``hooks`` (§D.1), so the tables it re-declares are pinned to their
sync-side twins here.
"""

from __future__ import annotations

import json

import pytest

from coding_agent_playbook.evals.run.agent_env import UNATTENDED_ENV_VAR as EVALS_UNATTENDED_ENV_VAR
from coding_agent_playbook.hook_runtime.combine import (
    ASK_DENIED_PREFIX,
    ASK_WARNED_PREFIX,
    OPENCODE_ASK_PREFIX,
    combine,
)
from coding_agent_playbook.hook_runtime.dispatch.caps import (
    LineCap,
    OutputCaps,
    clamp_lines,
    clean_text,
    clip,
    quote_data,
)
from coding_agent_playbook.hook_runtime.dispatch.decision import (
    EVENT_DECISIONS,
    CombinedResult,
    Decision,
    HandlerResult,
    supported_decision,
)
from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, EventName, Harness
from coding_agent_playbook.hook_runtime.dispatch.policy import (
    CLASS_RANK,
    ENGINE_DEADLINE_CAP_MS,
    ON_ERROR_ALLOWED,
    UNATTENDED_ENV_VAR,
    effective_on_error,
    failure_class,
    failure_decision,
    is_unattended,
)
from coding_agent_playbook.hooks.resolution.tables import (
    ENGINE_DEADLINE_CAP_MS as POLICY_DEADLINE_CAP_MS,
)
from coding_agent_playbook.hooks.resolution.tables import HOOK_EVENTS
from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after

D, A, C, N = Decision.DENY, Decision.ASK, Decision.CONTEXT, Decision.NONE


class FakeOnce:
    """``SessionState.once`` in memory: true the first time a key is seen; records calls."""

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.calls: list[str] = []

    def __call__(self, key: str) -> bool:
        self.calls.append(key)
        first = key not in self.seen
        self.seen.add(key)
        return first


def _ev(
    name: EventName = EventName.PRE_TOOL_USE,
    *,
    harness: Harness = Harness.CLAUDE_CODE,
    unattended: bool = False,
    permission_mode: str | None = None,
) -> CanonicalEvent:
    return CanonicalEvent(
        name=name,
        harness=harness,
        session_id="s-1",
        cwd="/r",
        project_dir="/r",
        unattended=unattended,
        permission_mode=permission_mode,
    )


def _r(decision: Decision, hook_id: str = "h", **fields: object) -> HandlerResult:
    return HandlerResult(decision=decision, hook_id=hook_id, **fields)  # type: ignore[arg-type]


# --- precedence and reasons -----------------------------------------------------------


def test_decision_precedence_is_deny_ask_context_none() -> None:
    assert sorted(Decision, key=lambda d: d.rank) == [N, C, A, D]
    assert combine([_r(C, context=("x",)), _r(A, reason="a"), _r(N)], ev=_ev()).decision is A


def test_no_results_is_none() -> None:
    assert combine([], ev=_ev()) == CombinedResult()


def test_deny_ask_context_yields_deny_with_4_line_clamp_and_more_findings_line() -> None:
    results = [
        _r(D, "guard-a", reason="a1\na2\na3"),
        _r(D, "guard-b", reason="b1\nb2"),
        _r(A, "guard-c", reason="c1"),
        _r(C, "lint-d", context=("ctx",), dedupe_key="k"),
    ]
    once = FakeOnce()

    combined = combine(results, ev=_ev(), once=once)

    assert combined.decision is D
    assert combined.reason.splitlines() == ["a1", "a2", "a3", "(+2 more playbook findings)"]
    assert combined.context == ()
    assert once.calls == []
    assert [o.effective for o in combined.outcomes] == [D, D, A, C]


def test_one_handler_with_too_many_lines_is_cut_without_a_summary_line() -> None:
    combined = combine([_r(D, reason="\n".join(f"l{i}" for i in range(9)))], ev=_ev())

    assert combined.reason.splitlines() == ["l0", "l1", "l2", "l3"]


@pytest.mark.parametrize("event", [EventName.STOP, EventName.SUBAGENT_STOP])
def test_stop_block_keeps_the_coordinators_40_line_reason(event: EventName) -> None:
    """The Stop coordinator's one combined reason has its own 40-line budget (§D.5.4)."""
    reason = "\n".join(f"[lint] line {i}" for i in range(45))

    combined = combine([_r(D, reason=reason)], ev=_ev(event))

    assert combined.reason.splitlines() == reason.splitlines()[: OutputCaps.STOP_REASON.max_lines]


def test_reason_lines_and_total_are_capped() -> None:
    combined = combine([_r(D, reason="\n".join(["x" * 300] * 4))], ev=_ev())
    lines = combined.reason.splitlines()

    assert all(len(line) <= OutputCaps.REASON.line_chars for line in lines)
    assert len(combined.reason) <= OutputCaps.REASON.max_chars
    assert lines[0].endswith("…")


def test_empty_deny_reason_names_the_hook() -> None:
    assert "guard-a" in combine([_r(D, "guard-a")], ev=_ev()).reason


# --- ask degradation ------------------------------------------------------------------


def test_ask_unattended_becomes_deny_with_needs_confirmation_prefix() -> None:
    combined = combine([_r(A, "guard-a", reason="force push")], ev=_ev(unattended=True))

    assert combined.decision is D
    assert combined.reason == f"{ASK_DENIED_PREFIX}force push"
    assert (combined.outcomes[0].decision, combined.outcomes[0].effective) == (A, D)
    assert combined.outcomes[0].contract_violation is False


def test_ask_on_opencode_uses_the_opencode_prefix() -> None:
    ev = _ev(harness=Harness.OPENCODE, unattended=True)

    assert combine([_r(A, reason="why")], ev=ev).reason == f"{OPENCODE_ASK_PREFIX}why"


def test_ask_attended_stays_ask() -> None:
    combined = combine([_r(A, reason="why")], ev=_ev())

    assert (combined.decision, combined.reason) == (A, "why")


def test_unattended_ask_warn_becomes_context_plus_user_note() -> None:
    combined = combine(
        [_r(A, "guard-a", reason="force push")],
        ev=_ev(unattended=True),
        unattended_ask="warn",
    )

    assert combined.decision is C
    assert combined.context == (f"{ASK_WARNED_PREFIX}force push",)
    assert len(combined.user_notes) == 1
    assert "guard-a" in combined.user_notes[0]
    assert combined.outcomes[0].effective is C


def test_ask_beside_a_deny_still_degrades_unattended() -> None:
    combined = combine(
        [_r(D, "a", reason="no"), _r(A, "b", reason="maybe")], ev=_ev(unattended=True)
    )

    assert combined.reason.splitlines() == ["no", f"{ASK_DENIED_PREFIX}maybe"]


# --- context --------------------------------------------------------------------------


@pytest.mark.parametrize("top", [D, A])
def test_context_dropped_under_deny_or_ask(top: Decision) -> None:
    once = FakeOnce()
    results = [_r(top, reason="r"), _r(C, context=("c1", "c2"), dedupe_key="k")]

    combined = combine(results, ev=_ev(), once=once)

    assert combined.decision is top
    assert combined.context == ()
    assert once.calls == []


def test_context_deduped_through_once_and_capped_5_project_8_total() -> None:
    once = FakeOnce()
    a = _r(C, "lint-a", context=tuple(f"a{i}" for i in range(7)), dedupe_key="src/a.py")
    b = _r(C, "lint-b", context=tuple(f"b{i}" for i in range(6)), dedupe_key="src/b.py")

    first = combine([a, b], ev=_ev(EventName.POST_TOOL_USE), once=once)

    assert first.context == ("a0", "a1", "a2", "a3", "a4", "b0", "b1", "b2")
    assert len(once.calls) == OutputCaps.CONTEXT_ITEMS_PER_EVENT

    second = combine([a, b], ev=_ev(EventName.POST_TOOL_USE), once=once)

    assert second.context == ("a5", "a6", "b3", "b4", "b5")


def test_context_without_a_dedupe_key_is_never_deduped_across_events() -> None:
    once = FakeOnce()
    result = _r(C, context=("same",))

    for _ in range(2):
        assert combine([result], ev=_ev(), once=once).context == ("same",)
    assert once.calls == []


def test_without_once_every_keyed_item_is_shown_every_time() -> None:
    result = _r(C, context=("same",), dedupe_key="k")

    assert combine([result], ev=_ev()).context == combine([result], ev=_ev()).context == ("same",)


def test_blank_items_and_non_context_results_add_no_context() -> None:
    combined = combine([_r(N, user_note="n"), _r(C, context=("", " \t ", "real"))], ev=_ev())

    assert (combined.decision, combined.context) == (C, ("real",))


def test_identical_context_items_within_an_event_appear_once() -> None:
    combined = combine([_r(C, "a", context=("dup",)), _r(C, "b", context=("dup",))], ev=_ev())

    assert combined.context == ("dup",)


def test_context_fully_deduped_away_yields_none() -> None:
    once = FakeOnce()
    result = _r(C, context=("seen",), dedupe_key="k")
    combine([result], ev=_ev(), once=once)

    assert combine([result], ev=_ev(), once=once).decision is N


# --- user notes -----------------------------------------------------------------------


def test_user_notes_deduped_6_lines_800_chars() -> None:
    results = [_r(N, f"h{i}", user_note=f"note {i}") for i in range(8)]
    results.append(_r(N, "dup", user_note="note 0"))

    combined = combine(results, ev=_ev())

    assert combined.decision is N
    assert combined.user_notes == tuple(f"note {i}" for i in range(6))

    long_notes = combine([_r(N, f"h{i}", user_note="x" * 300 + str(i)) for i in range(4)], ev=_ev())

    assert len("\n".join(long_notes.user_notes)) <= OutputCaps.USER_NOTES.max_chars


def test_user_notes_survive_a_deny() -> None:
    combined = combine([_r(D, reason="no", user_note="heads up")], ev=_ev())

    assert combined.user_notes == ("heads up",)


# --- event support --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("event", "raw", "expected"),
    [
        (EventName.POST_TOOL_USE, D, C),
        (EventName.POST_TOOL_USE, A, C),
        (EventName.SESSION_START, D, C),
        (EventName.STOP, A, D),
        (EventName.USER_PROMPT_SUBMIT, A, D),
        (EventName.PRE_COMPACT, C, N),
        (EventName.SESSION_END, D, N),
    ],
)
def test_event_support_maps_decision_down_and_flags_contract_violation(
    event: EventName, raw: Decision, expected: Decision
) -> None:
    combined = combine([_r(raw, reason="why", context=("ctx",))], ev=_ev(event))

    assert combined.decision is expected
    assert combined.outcomes[0].contract_violation is True
    assert combined.outcomes[0].effective is expected
    if expected is C:
        assert "why" in combined.context


@pytest.mark.parametrize("event", list(EventName))
def test_supported_decision_keeps_every_allowed_decision(event: EventName) -> None:
    for decision in EVENT_DECISIONS[event]:
        assert supported_decision(event, decision) is decision
        assert (
            combine([_r(decision, reason="r", context=("c",))], ev=_ev(event))
            .outcomes[0]
            .contract_violation
            is False
        )


def test_event_decisions_match_the_hooks_tables() -> None:
    runtime = {
        event.value: {d.value for d in allowed} for event, allowed in EVENT_DECISIONS.items()
    }

    assert runtime == {name: set(spec.decisions) for name, spec in HOOK_EVENTS.items()}


def test_degraded_results_are_marked_in_their_outcome() -> None:
    combined = combine([_r(A, "guard-a", reason="failed", degraded=True)], ev=_ev())

    assert combined.outcomes[0].degraded is True


# --- caps and sanitization ------------------------------------------------------------


def test_quote_data_truncates_and_escapes_control_chars() -> None:
    assert quote_data("a\nb\x1b[31m") == '"a\\nb\\u001b[31m"'
    assert quote_data("café") == '"caf\\u00e9"'
    assert json.loads(quote_data("x" * 500)) == "x" * OutputCaps.QUOTE_CHARS
    assert json.loads(quote_data("abcdef", limit=3)) == "abc"


def test_clean_text_replaces_control_characters_but_keeps_newlines() -> None:
    assert clean_text("a\x1b[2Jb\tc\r\nd\x7f") == "a [2Jb c \nd "


def test_clip_marks_a_cut_with_an_ellipsis() -> None:
    assert clip("abcdef", 4) == "abc…"
    assert clip("abc", 4) == "abc"


def test_clamp_lines_drops_blank_lines_and_summarizes_the_rest() -> None:
    cap = OutputCaps.REASON
    lines = ["one", "", "  ", "two", "three", "four", "five"]

    assert clamp_lines(lines, cap) == ("one", "two", "three", "four")
    assert clamp_lines(lines, cap, summary=lambda n: f"+{n}") == ("one", "two", "three", "+2")


def test_clamp_lines_drops_more_lines_until_the_summary_fits_the_budget() -> None:
    clamped = clamp_lines(["a" * 10] * 5, LineCap(4, 32, 10), summary=lambda n: f"(+{n} more)")

    assert clamped == ("a" * 10, "a" * 10, "(+3 more)")


@pytest.mark.parametrize(("lines", "chars", "line"), [(0, 10, 5), (2, 10, 11), (2, 10, 0)])
def test_line_cap_rejects_an_impossible_budget(lines: int, chars: int, line: int) -> None:
    with pytest.raises(ValueError, match=f"line_chars={line}"):
        LineCap(lines, chars, line)


# --- unattended -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "harness", "mode", "expected"),
    [
        ({}, Harness.CLAUDE_CODE, None, False),
        ({"PLAYBOOK_HOOK_UNATTENDED": "1"}, Harness.CLAUDE_CODE, None, True),
        ({"PLAYBOOK_HOOK_UNATTENDED": "true"}, Harness.CLAUDE_CODE, None, False),
        ({"CI": "true"}, Harness.CLAUDE_CODE, None, True),
        ({"CI": "1"}, Harness.CLAUDE_CODE, None, True),
        ({"CI": "0"}, Harness.CLAUDE_CODE, None, False),
        ({"GITHUB_ACTIONS": "true"}, Harness.CLAUDE_CODE, None, True),
        ({}, Harness.OPENCODE, None, True),
        ({}, Harness.CLAUDE_CODE, "dontAsk", True),
        ({}, Harness.CLAUDE_CODE, "bypassPermissions", False),
        ({}, Harness.CLAUDE_CODE, "auto", False),
    ],
)
def test_is_unattended_signals(
    env: dict[str, str], harness: Harness, mode: str | None, expected: bool
) -> None:
    assert is_unattended(_ev(harness=harness, permission_mode=mode), env) is expected


def test_unattended_env_var_matches_the_eval_runners() -> None:
    assert UNATTENDED_ENV_VAR == EVALS_UNATTENDED_ENV_VAR


# --- failure-policy tables ------------------------------------------------------------


@pytest.mark.parametrize("event", list(EventName))
@pytest.mark.parametrize("declared", ["ask", "deny", "open"])
def test_on_error_clamped_to_open_on_open_only_events(event: EventName, declared: str) -> None:
    allowed = ON_ERROR_ALLOWED[event]
    expected = declared if declared in allowed else "open"

    assert effective_on_error(declared, event) == expected
    if allowed == {"open"}:
        assert effective_on_error(declared, event) == "open"


def test_unknown_on_error_value_fails_open() -> None:
    assert effective_on_error("explode", EventName.PRE_TOOL_USE) == "open"


def test_on_error_table_matches_the_hooks_tables() -> None:
    runtime = {event.value: set(allowed) for event, allowed in ON_ERROR_ALLOWED.items()}

    assert runtime == {name: set(spec.on_error_allowed) for name, spec in HOOK_EVENTS.items()}


def test_failure_class_mapping_and_rank() -> None:
    assert [failure_class(v) for v in ("ask", "deny", "open")] == [
        "guard",
        "guard_strict",
        "quality",
    ]
    assert [failure_decision(c) for c in ("guard", "guard_strict", "quality")] == [A, D, N]
    assert CLASS_RANK["guard"] == CLASS_RANK["guard_strict"] < CLASS_RANK["quality"]


def test_engine_deadline_caps_match_the_hooks_tables() -> None:
    assert {event.value: cap for event, cap in ENGINE_DEADLINE_CAP_MS.items()} == dict(
        POLICY_DEADLINE_CAP_MS
    )


# --- import budget --------------------------------------------------------------------


def test_decision_modules_import_only_the_stdlib_and_the_runtime() -> None:
    loaded = new_modules_after(
        "import coding_agent_playbook.hook_runtime.combine, "
        "coding_agent_playbook.hook_runtime.dispatch.policy, "
        "coding_agent_playbook.hook_runtime.dispatch.caps"
    )
    engine = {m for m in loaded if m.startswith("coding_agent_playbook.")}

    runtime = engine_module("coding_agent_playbook.hook_runtime")
    assert all(m.startswith(runtime) for m in engine), engine
    assert not {"tomllib", "argparse", "importlib.metadata", "jinja2", "yaml"} & set(loaded)
