"""pii-prompt-guard: block a prompt carrying checksum-validated PII (specs/prK-hook-pack.md §E.5).

An overlay-tier mechanism: the engine ships it inert (``tier: overlay``, no
detectors, ``on_error: open``) and a regulated overlay activates it with a
same-id override that promotes it to ``tier: default``, names the detectors
and raises ``on_error`` to ``deny`` (H10, OQ-18). Claude only: OpenCode does not
render ``user_prompt_submit`` in v1 (QC-2).

- The detectors are ``security.pii``'s (checksums keep false positives low;
  published test values never count). A hit is a ``deny``, which Claude
  renders as ``decision: "block"``: the reason is shown to the user, not the
  model, and gives each hit's category, offset and masked form, never the value.
- Only the first ``max_prompt_bytes`` are scanned (in chunks), so a huge paste
  stays within the hook's budget. A longer prompt cannot be checked whole, so
  it is blocked as well: the guard fails closed once activated.
- ``override_token`` in the prompt lets a blocked prompt through: the result
  is ``none`` with the ``override_token`` escape marker, which the decision
  log records by category only (an empty token disables the override).
- An internal error (a bad overlay row included) goes through the failure
  policy; with the overlay's ``on_error: deny`` it blocks with
  :data:`FAILURE_REASON` (``FAILURE_REASON`` of the declaration).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.security.pii import mask, pii_config, scan_pii

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.security.pii import PiiConfig, PiiMatch

__all__ = [
    "CONFIG_SCHEMA",
    "DEFAULT_MAX_PROMPT_BYTES",
    "FAILURE_REASON",
    "OVERRIDE_ESCAPE",
    "OVERSIZE_RULE",
    "PromptScan",
    "block_reason",
    "pii_prompt_guard",
    "scan_prompt",
]

#: What the user sees when the guard itself fails (§E.5), instead of the generic reason.
FAILURE_REASON: Final = "PII guard error; resubmit or use the override"
DEFAULT_MAX_PROMPT_BYTES: Final = 1024 * 1024
#: The decision-log escape marker of an honoured override token (never the token).
OVERRIDE_ESCAPE: Final = "override_token"
#: The category of a prompt too large to check whole.
OVERSIZE_RULE: Final = "oversize"
#: Hits listed in the reason before the rest are counted: two fit one 160-character line.
_LISTED: Final = 2

#: Detectors and rows are deny tables (``extend``); the test-value allowlist and
#: the override token loosen the guard (``relax``: a mandatory hook ignores the
#: consumer's). ``max_prompt_bytes`` either way stays fail-closed.
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "detectors": ConfigKey("list", "extend"),
    "extra_detectors": ConfigKey("list", "extend"),
    "test_value_allowlist": ConfigKey("list", "relax"),
    "override_token": ConfigKey("string", "relax"),
    "max_prompt_bytes": ConfigKey("integer"),
}


@dataclass(frozen=True, slots=True)
class PromptScan:
    """What the guard found in one prompt: the hits in its scanned head, its size, the cap.

    Example::

        >>> scan = scan_prompt("pay GB33BUKB20201555555555", PiiConfig(), max_bytes=1024)
        >>> (scan.blocked, scan.categories())  # doctest: +SKIP
        (True, ('iban',))
    """

    matches: tuple[PiiMatch, ...]
    size: int
    cap: int

    @property
    def oversize(self) -> bool:
        """Whether part of the prompt went unscanned."""
        return self.size > self.cap

    @property
    def blocked(self) -> bool:
        """A hit, or a prompt too large to check whole."""
        return bool(self.matches) or self.oversize

    def categories(self) -> tuple[str, ...]:
        """The detectors that hit, sorted, plus :data:`OVERSIZE_RULE` when oversize."""
        found = sorted({match.detector for match in self.matches})
        return (*found, OVERSIZE_RULE) if self.oversize else tuple(found)


def scan_prompt(prompt: str, cfg: PiiConfig, *, max_bytes: int) -> PromptScan:
    """Scan the first ``max_bytes`` (UTF-8) of ``prompt`` with ``cfg``'s detectors.

    Offsets are character offsets into ``prompt``: the scanned head is an
    exact prefix of it, cut on a character boundary.

    Example::

        >>> scan_prompt("x" * 10, PiiConfig(), max_bytes=4).oversize
        True
    """
    head, size = _head(prompt, max_bytes)
    return PromptScan(tuple(scan_pii(head, cfg)), size, max_bytes)


def _head(prompt: str, max_bytes: int) -> tuple[str, int]:
    """The longest character prefix of ``prompt`` within ``max_bytes``, and its whole size."""
    data = prompt.encode("utf-8", "surrogatepass")  # lone surrogates survive a JSON payload
    if len(data) <= max_bytes:
        return prompt, len(data)
    cut = max_bytes
    while cut > 0 and (data[cut] & 0xC0) == 0x80:  # a continuation byte starts no character
        cut -= 1
    return data[:cut].decode("utf-8", "surrogatepass"), len(data)


def block_reason(scan: PromptScan) -> str:
    """The user-facing reason: category, offset and masked form per hit, never a value.

    Short lines, because a deny reason is capped at 4 lines of 160 characters
    (§D.3.4): what was found, the first hits, then what to do.

    Example::

        >>> print(block_reason(scan))  # doctest: +SKIP
        Prompt not sent: it contains personal data.
        iban at offset 4: GB** **** **** **** **** 55
        Resubmit with a placeholder such as <IBAN> instead of the value, or use the override.
    """
    if not scan.matches:
        return (
            f"Prompt not sent: it is {scan.size} bytes, over the PII guard's {scan.cap}-byte "
            "limit, so it cannot be checked for personal data.\n"
            "Shorten it, or use the override."
        )
    hits = [f"{m.detector} at offset {m.start}: {mask(m)}" for m in scan.matches[:_LISTED]]
    more = len(scan.matches) - _LISTED
    listed = "; ".join(hits) + (f" (+{more} more)" if more > 0 else "")
    partial = f" Only the first {scan.cap} bytes were checked." if scan.oversize else ""
    return (
        f"Prompt not sent: it contains personal data.{partial}\n{listed}\n"
        "Resubmit with a placeholder such as <IBAN> instead of the value, or use the override."
    )


@register_hook_handler(
    "pii_prompt_guard",
    events=["user_prompt_submit"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
    failure_reason=FAILURE_REASON,
)
def pii_prompt_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Block ``ev``'s prompt when it carries PII or is too large to check (module docstring).

    Raises ``ValueError`` on a bad overlay row: an internal error for the
    failure policy, which blocks under the overlay's ``on_error: deny``.

    Example: ``pii_prompt_guard(prompt_with_iban, ctx).decision is Decision.DENY``.
    """
    if not ev.prompt:
        return None
    cfg = pii_config(ctx.config)
    if not cfg.finders():
        return None  # the engine's inert definition: nothing to look for
    scan = scan_prompt(ev.prompt, cfg, max_bytes=_max_bytes(ctx.config))
    if not scan.blocked:
        return None
    rule_id = ",".join(scan.categories())
    if _overridden(ev.prompt, ctx.config):
        return HandlerResult(
            decision=Decision.NONE, hook_id=ctx.hook.id, rule_id=rule_id, escape=OVERRIDE_ESCAPE
        )
    return HandlerResult(
        decision=Decision.DENY, hook_id=ctx.hook.id, rule_id=rule_id, reason=block_reason(scan)
    )


def _overridden(prompt: str, config: Mapping[str, object]) -> bool:
    token = config.get("override_token")
    return isinstance(token, str) and bool(token.strip()) and token in prompt


def _max_bytes(config: Mapping[str, object]) -> int:
    value = config.get("max_prompt_bytes")
    if type(value) is int and value > 0:
        return value
    return DEFAULT_MAX_PROMPT_BYTES
