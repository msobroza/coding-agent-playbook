"""The cross-section golden for ``playbook.hook.wire/1`` (specs/prK-lifecycle-hooks.md §C.7, §D.3.5, §C.3.2).

The dispatcher's ``render_opencode`` writes the wire and the OpenCode shim's
``parse()`` reads it. Both sides are pinned here:

- every rendered result goes through the line-for-line Python port kept beside
  the template (always) and through the template's own marker-delimited slice
  under node (when present), and the two must agree on every case;
- the port carries the slice's sha256, so an edit to ``parse()`` in JS fails
  until the port has been reviewed against it;
- the shim's ``TOOL``/``ALIAS``/``EVENT`` literals equal the Python tables the
  dispatcher parses with and the hook-policy OpenCode column.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from coding_agent_playbook.hook_registrations import OPENCODE_REG_EVENTS
from coding_agent_playbook.hook_registrations._templates import shim_template
from coding_agent_playbook.hook_runtime.decision import CombinedResult, Decision
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.harness import CLAUDE_EVENT_NAMES, DENY_EXIT
from coding_agent_playbook.hook_runtime.harness._render import DEFAULT_REASONS
from coding_agent_playbook.hook_runtime.harness._tools import TOOL_CLASSES, classify
from coding_agent_playbook.hook_runtime.harness.opencode import (
    NATIVE_TOOL_NAMES,
    V1_ARG_ALIASES,
    render_opencode,
)
from coding_agent_playbook.hooks.resolution.tables import HOOK_SUPPORT, TOOL_CLASS_NAMES
from coding_agent_playbook.templates.hook_shims.opencode_wire_port import (
    CAP,
    DEFAULT_REASON,
    PARSE_JS_SHA256,
    WIRE_BEGIN,
    WIRE_END,
    WireParse,
    WireSlice,
    parse_wire,
    slice_sha256,
    wire_slice,
)
from tests.node_kit import needs_node, run_node

_TEMPLATE = shim_template("opencode-plugin.js")
_SRC = Path(__file__).resolve().parents[2] / "src" / "coding_agent_playbook"
_PORT_MODULE = "opencode_wire_port"
_NOT_JSON = "dispatcher wrote non-JSON stdout"
_GRIN = "\U0001f600"  # one astral character: two UTF-16 code units in JS
_BOM = chr(0xFEFF)
#: "keep" between JS whitespace Python's own strip() disagrees on (BOM) or shares (Zs, LS).
_PADDED = chr(0x3000) + _BOM + " keep " + chr(0x2028) + chr(0x00A0)


def _wire(
    event: EventName,
    *,
    decision: Decision = Decision.NONE,
    reason: str = "",
    context: tuple[str, ...] = (),
    user_notes: tuple[str, ...] = (),
) -> tuple[int, str]:
    """``render_opencode``'s ``(exit code, stdout)`` for a hand-built combined result."""
    combined = CombinedResult(
        decision=decision, reason=reason, context=context, user_notes=user_notes
    )
    output = render_opencode(event, combined)
    return output.exit_code, output.stdout


def _hand(**body: object) -> str:
    """A wire stdout written by hand, for what the renderer never produces."""
    return json.dumps(body)


def _inactive(why: str) -> WireParse:
    return WireParse("none", "", "", "", failed=why)


# --- the renderer -> parse() golden ----------------------------------------------------


@pytest.mark.parametrize("decision", [Decision.DENY, Decision.ASK], ids=["deny", "ask"])
def test_deny_wire_parses_to_deny_with_reason(decision: Decision) -> None:
    code, out = _wire(EventName.PRE_TOOL_USE, decision=decision, reason="rm -rf is blocked")

    assert code == DENY_EXIT  # OpenCode has no ask primitive: an ask is a deny here
    assert parse_wire(code, out) == WireParse("deny", "rm -rf is blocked", "", "")


def test_stop_deny_exit_0_parses_to_deny_for_carry() -> None:
    code, out = _wire(EventName.STOP, decision=Decision.DENY, reason="ruff: 2 errors\nmypy: ok")

    assert code == 0  # session.idle cannot block: the shim carries it into the next turn
    assert parse_wire(code, out) == WireParse("deny", "ruff: 2 errors\nmypy: ok", "", "")


def test_context_lines_joined_and_capped_at_4000() -> None:
    short = _wire(EventName.POST_TOOL_USE, decision=Decision.CONTEXT, context=("E501 a.py:3", "ok"))
    long = _wire(
        EventName.PRE_TOOL_USE, decision=Decision.CONTEXT, context=("a" * 3000, "b" * 3000)
    )
    hand = _hand(v=1, decision="context", context=["x" * 3000, "y" * 3000])

    assert parse_wire(*short) == WireParse("none", "", "E501 a.py:3\nok", "")
    assert parse_wire(*long).context == "a" * 3000 + "\n" + "b" * 998 + "…"
    assert parse_wire(0, hand).context == "x" * 3000 + "\n" + "y" * (CAP - 3001)
    assert CAP == 4000


def test_notice_is_forwarded_and_capped() -> None:
    rendered = _wire(EventName.SESSION_START, user_notes=("pin is stale", "run doctor"))
    hand = _hand(v=1, decision="none", notice="n" * 5000)

    assert parse_wire(*rendered) == WireParse("none", "", "", "pin is stale\nrun doctor")
    assert parse_wire(0, hand).notice == "n" * CAP


@pytest.mark.parametrize("code", [2, 1, 3, 127, None], ids=["raw2", "1", "3", "127", "signal"])
def test_raw_exit_2_is_inactive_never_deny(code: int | None) -> None:
    out = _hand(v=1, decision="deny", reason="looks like a deny")
    shown = "null" if code is None else str(code)

    assert parse_wire(code, out) == _inactive(f"dispatcher exited {shown}")


@pytest.mark.parametrize("out", ["", "\n", " \t\r\n", "{}", _hand(reason="   ")])
def test_exit_10_with_empty_stdout_denies_with_default_reason(out: str) -> None:
    assert parse_wire(DENY_EXIT, out) == WireParse("deny", DEFAULT_REASON, "", "")
    assert DEFAULT_REASONS[Decision.DENY] == DEFAULT_REASON


@pytest.mark.parametrize("code", [0, DENY_EXIT])
@pytest.mark.parametrize(
    "out", ["not json", "[1]", "null", "42", '"deny"', "true", "NaN", "Infinity", "{", "{}{}"]
)
def test_non_json_stdout_is_inactive(code: int, out: str) -> None:
    assert parse_wire(code, out) == _inactive(_NOT_JSON)


@pytest.mark.parametrize("event", OPENCODE_REG_EVENTS)
@pytest.mark.parametrize("decision", list(Decision))
def test_only_a_rendered_deny_parses_to_deny(event: str, decision: Decision) -> None:
    code, out = _wire(EventName(event), decision=decision, reason="r", context=("c",))

    parsed = parse_wire(code, out)

    assert parsed.failed is None  # a rendered result is never a harness-level failure
    assert (parsed.decision == "deny") == (json.loads(out)["decision"] == "deny")


def test_parse_reads_only_string_fields() -> None:
    out = _hand(
        decision="deny",
        reason={"toString": 1},
        context=["a", 1, None, ["b"], {"c": 1}, "d"],
        notice=42,
    )

    assert parse_wire(0, out) == WireParse("deny", DEFAULT_REASON, "a\nd", "")


def test_trim_and_cap_follow_js_string_semantics() -> None:
    padded = _hand(decision="deny", reason=_PADDED)
    astral = _hand(context=[_GRIN * 2500], notice="a" + _GRIN * 2000)

    assert parse_wire(0, padded).reason == "keep"
    assert parse_wire(0, astral).context == _GRIN * 2000  # CAP UTF-16 code units, as JS slices
    assert parse_wire(0, astral).notice == "a" + _GRIN * 1999 + "\ud83d"


def test_inactive_warns_once_per_process() -> None:
    port = WireSlice()

    port.parse(2, "")
    port.parse(0, "garbage")

    assert port.errors == [
        "[playbook] lifecycle hooks inactive: dispatcher exited 2; run 'playbook-hook doctor'"
    ]


# --- the port is pinned to the template's slice ------------------------------------------


def test_port_is_pinned_to_template_parse_slice() -> None:
    assert slice_sha256(_TEMPLATE) == PARSE_JS_SHA256, (
        "parse() in templates/hook_shims/opencode-plugin.js changed: review "
        "opencode_wire_port.py line for line, then update PARSE_JS_SHA256"
    )


@pytest.mark.parametrize(
    "text",
    ["no markers", f"{WIRE_BEGIN}\n{WIRE_BEGIN}\n{WIRE_END}\n", f"{WIRE_END}\n{WIRE_BEGIN}\n"],
    ids=["missing", "twice", "reversed"],
)
def test_wire_slice_requires_one_ordered_marker_pair(text: str) -> None:
    with pytest.raises(ValueError, match="wire-parse markers"):
        wire_slice(text)


def test_port_is_never_imported_by_the_engine() -> None:
    importers = [
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if path.stem != _PORT_MODULE and _PORT_MODULE in path.read_text(encoding="utf-8")
    ]

    assert importers == []


# --- the same cases under node ------------------------------------------------------------

_NODE_DRIVER = """\
import { readFileSync } from "node:fs"
%s
const errors = []
console.error = (...parts) => { errors.push(parts.join(" ")) }
const cases = JSON.parse(readFileSync(0, "utf8"))
const results = cases.map(([code, out]) => parse(code, out))
process.stdout.write(JSON.stringify({ results, errors }))
"""


def _node_cases() -> list[tuple[int | None, str]]:
    rendered = [
        _wire(
            EventName(event),
            decision=decision,
            reason=" r ",
            context=("c1", "c2"),
            user_notes=("n",),
        )
        for event in OPENCODE_REG_EVENTS
        for decision in Decision
    ]
    hand = [
        (2, _hand(decision="deny")),
        (None, ""),
        (DENY_EXIT, ""),
        (DENY_EXIT, "\n"),
        (0, "not json"),
        (0, "NaN"),
        (0, "[1]"),
        (0, "null"),
        (
            0,
            _hand(decision="deny", reason={"toString": 1}, context=["a", 1, None, ["b"]], notice=4),
        ),
        (0, _hand(decision="deny", reason=_PADDED)),
        (0, _hand(context=[_GRIN * 2500], notice="a" + _GRIN * 2000)),
        (0, _hand(context=["x" * 3000, "y" * 3000], notice="n" * 5000)),
        (0, _BOM + _hand(decision="deny", reason="bom")),
    ]
    return [*rendered, *hand]


@needs_node
def test_python_port_matches_node_parse(tmp_path: Path) -> None:
    cases = _node_cases()
    module = tmp_path / "wire-parse.mjs"
    module.write_text(_NODE_DRIVER % wire_slice(_TEMPLATE), encoding="utf-8")
    port = WireSlice()

    done = run_node([str(module)], stdin=json.dumps(cases))

    assert done.returncode == 0, done.stderr
    expected = [port.parse(code, out).as_json() for code, out in cases]
    assert json.loads(done.stdout) == {"results": expected, "errors": port.errors}


# --- the shim's tables equal the dispatcher's ---------------------------------------------


def _js_table(name: str) -> dict[str, str]:
    """The template's ``const <name> = { key: "value", ... }`` literal as a dict."""
    match = re.search(rf"^const {name} = \{{(.*?)\}}", _TEMPLATE, flags=re.MULTILINE | re.DOTALL)
    assert match is not None, f"no const {name} table in the shim template"
    return dict(re.findall(r'(\w+): "([^"]*)"', match.group(1)))


def test_shim_tables_match_runtime_parser_and_hooks_tables() -> None:
    tool, alias, event = _js_table("TOOL"), _js_table("ALIAS"), _js_table("EVENT")
    column = {name for row in TOOL_CLASS_NAMES.values() for name in row["opencode"]}

    assert set(tool) == set(NATIVE_TOOL_NAMES.values())
    assert all(NATIVE_TOOL_NAMES[claude] == native for native, claude in tool.items())
    assert alias == dict(V1_ARG_ALIASES)
    assert event == {e: CLAUDE_EVENT_NAMES[EventName(e)] for e in OPENCODE_REG_EVENTS}
    assert set(event) == set(HOOK_SUPPORT["opencode"])
    # Every native name in the policy column is classified as its class once the shim maps it.
    for tool_class, row in TOOL_CLASS_NAMES.items():
        for native in row["opencode"]:
            assert tool_class in {c.value for c in classify(tool.get(native, native))}
    assert column - set(tool) == {"apply_patch"} and "apply_patch" in TOOL_CLASSES
