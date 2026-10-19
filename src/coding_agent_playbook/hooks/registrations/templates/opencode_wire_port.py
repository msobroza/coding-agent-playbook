"""A line-for-line Python port of the OpenCode shim's ``parse()`` (specs/prK-lifecycle-hooks.md §C.7, §D.3.5).

A test oracle, never imported by the engine. ``tests/hook_runtime/test_wire_contract.py``
feeds ``render_opencode`` output through it (always) and through the
template's own marker-delimited slice under node (when present), and requires
identical results. :data:`PARSE_JS_SHA256` pins the slice this port was
reviewed against, so an edit to ``parse()`` in ``opencode-plugin.js`` fails
that test until the port is reviewed again. It lives beside the template, as
§C.7 asks, because the two must change together.

JS semantics are ported where Python's differ: ``String.prototype.trim``
strips JS whitespace (the BOM included), ``slice`` counts UTF-16 code units
(so a cut can split a surrogate pair), and ``JSON.parse`` rejects ``NaN`` and
``Infinity``. The one divergence left is Python's recursion limit: a document
nested deeper than it reads as non-JSON here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Final, Literal

__all__ = [
    "CAP",
    "DEFAULT_REASON",
    "PARSE_JS_SHA256",
    "WIRE_BEGIN",
    "WIRE_END",
    "WireParse",
    "WireSlice",
    "parse_wire",
    "slice_sha256",
    "wire_slice",
]

#: The comment lines around the slice in the template (and in every rendered shim).
WIRE_BEGIN: Final = "// @@wire-parse:begin"
WIRE_END: Final = "// @@wire-parse:end"
#: sha256 of :func:`wire_slice` of the template this port was reviewed against.
PARSE_JS_SHA256: Final = "e5be154933a43594b2699fd20a82ec122a716e933bafbe96de6fc044f993d4f2"

#: ``const CAP``: the ceiling per injected block, in UTF-16 code units.
CAP: Final = 4000
#: The reason a deny without one gets; equal to the dispatcher's own default.
DEFAULT_REASON: Final = "Blocked by a playbook hook."
_DENY_EXIT: Final = 10
_NON_JSON: Final = "dispatcher wrote non-JSON stdout"
#: What ``String.prototype.trim`` strips: ECMAScript WhiteSpace (all of Zs) and LineTerminator.
_JS_WHITESPACE: Final = "\t\n\v\f\r " + "".join(
    map(
        chr,
        (0x00A0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF),
    )
)


@dataclass(frozen=True, slots=True)
class WireParse:
    """What ``parse()`` returns; ``failed`` is set only by ``inactive()``.

    Example: ``WireParse("deny", "Blocked by a playbook hook.", "", "").failed is None``.
    """

    decision: Literal["deny", "none"]
    reason: str
    context: str
    notice: str
    failed: str | None = None

    def as_json(self) -> dict[str, str]:
        """The JS result object's own keys, as ``JSON.stringify`` writes them.

        Example: ``WireParse("none", "", "", "").as_json()["decision"] == "none"``.
        """
        body = {
            "decision": self.decision,
            "reason": self.reason,
            "context": self.context,
            "notice": self.notice,
        }
        if self.failed is not None:
            body["failed"] = self.failed
        return body


@dataclass
class WireSlice:
    """The slice's module state, ``let warned``, and what its ``console.error`` printed.

    One instance stands for one shim process: ``inactive()`` warns only once.

    Example::

        >>> port = WireSlice()
        >>> port.parse(10, "").decision
        'deny'
    """

    warned: bool = False
    errors: list[str] = field(default_factory=list)

    def inactive(self, why: str) -> WireParse:
        """``inactive(why)``: fail open, saying so once per process."""
        if not self.warned:
            self.warned = True
            self.errors.append(
                f"[playbook] lifecycle hooks inactive: {why}; run 'playbook-hook doctor'"
            )
        return WireParse("none", "", "", "", failed=why)

    def parse(self, code: int | None, out: str) -> WireParse:
        """``parse(code, out)``: exit 10 is a decided deny; any exit but 0 and 10 is inactive.

        ``code`` is ``None`` where node's ``close`` reports ``null`` (a signal).
        """
        if code not in (0, _DENY_EXIT):
            return self.inactive(f"dispatcher exited {'null' if code is None else code}")
        text = _js_trim(out)
        j = _json_object(text) if text else {}
        if j is None:
            return self.inactive(_NON_JSON)
        deny = code == _DENY_EXIT or j.get("decision") == "deny"
        context = j.get("context")
        lines = [c for c in context if isinstance(c, str)] if isinstance(context, list) else []
        return WireParse(
            decision="deny" if deny else "none",
            reason=_js_trim(_str(j.get("reason"))) or (DEFAULT_REASON if deny else ""),
            context=_js_slice("\n".join(lines), CAP),
            notice=_js_slice(_str(j.get("notice")), CAP),
        )


def parse_wire(code: int | None, out: str) -> WireParse:
    """``parse(code, out)`` in a fresh shim process.

    Example::

        >>> parse_wire(2, '{"decision": "deny"}').failed
        'dispatcher exited 2'
    """
    return WireSlice().parse(code, out)


def wire_slice(shim_text: str) -> str:
    """The lines strictly between the one ``WIRE_BEGIN``/``WIRE_END`` pair, each ending in LF.

    Raises ValueError, with the marker counts, unless exactly one ordered pair exists.

    Example: ``wire_slice(f"{WIRE_BEGIN}\\nlet a = 1\\n{WIRE_END}\\n") == "let a = 1\\n"``.
    """
    lines = shim_text.split("\n")
    begins, ends = lines.count(WIRE_BEGIN), lines.count(WIRE_END)
    if begins != 1 or ends != 1 or lines.index(WIRE_BEGIN) > lines.index(WIRE_END):
        raise ValueError(
            f"expected one ordered pair of wire-parse markers, found {begins} begin and {ends} end"
        )
    body = lines[lines.index(WIRE_BEGIN) + 1 : lines.index(WIRE_END)]
    return "".join(f"{line}\n" for line in body)


def slice_sha256(shim_text: str) -> str:
    """The sha256 hex digest of :func:`wire_slice` of ``shim_text``, UTF-8 encoded.

    Example: ``slice_sha256(template) == PARSE_JS_SHA256`` while the port is current.
    """
    return hashlib.sha256(wire_slice(shim_text).encode("utf-8")).hexdigest()


def _str(value: object) -> str:
    """``str(v)``: a string wire field as is, anything else dropped."""
    return value if isinstance(value, str) else ""


def _js_trim(text: str) -> str:
    return text.strip(_JS_WHITESPACE)


def _js_slice(text: str, end: int) -> str:
    """``text.slice(0, end)``, counted in UTF-16 code units as JS does."""
    units = text.encode("utf-16-le", "surrogatepass")
    if len(units) <= 2 * end:
        return text
    return units[: 2 * end].decode("utf-16-le", "surrogatepass")


def _json_object(text: str) -> dict[str, object] | None:
    """``JSON.parse(text)`` when it yields a plain object, else ``None``."""
    try:
        value = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _reject_constant(name: str) -> object:
    raise ValueError(f"JSON.parse rejects {name}")
