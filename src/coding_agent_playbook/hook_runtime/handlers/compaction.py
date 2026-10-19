"""precompact-checkpoint: the user's own constraints survive compaction (specs/prK-hook-pack.md §E.5).

Opt-in, Claude only (``PreCompact`` and ``SessionStart`` with source
``compact``; OpenCode has no transcript to re-read, §C.1.2).

- ``pre_compact`` (:func:`precompact_checkpoint`) stores **no message text**:
  the :class:`EntryRef` (uuid and byte offset) of each of the last
  ``max_prompts`` genuine human prompts (``_transcript_prompts``) plus the
  repo-relative files this session edited (from the ledger), in
  ``<state>/checkpoints/<sha256(session)[:16]>.json``.
- ``session_start`` source ``compact`` (:func:`precompact_reinject`) re-reads
  those entries from ``transcript_path``, masks secret tokens (and PII when an
  overlay listed detectors in ``pii``), and injects one context item: one
  ``Before compaction the user said: "..."`` line per prompt, each a
  :func:`~coding_agent_playbook.hook_runtime.caps.quote_data` literal (control
  characters and newlines cannot survive), plus the edited files.

Any surprise in the unversioned transcript fails open: no checkpoint, no
injection. Stale checkpoints are TTL-pruned at session start with the rest of
the state root (``state._sweep``). No LLM, no network, stdlib JSONL only.
"""

from __future__ import annotations

import re
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.caps import (
    LineCap,
    clamp_lines,
    clean_text,
    clip,
    quote_data,
)
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.handlers._pii_settings import (
    PII_CONFIG_KEY,
    PII_KEY,
    pii_settings,
)
from coding_agent_playbook.hook_runtime.handlers._transcript_prompts import (
    EntryRef,
    TranscriptShapeError,
    read_prompts,
    select_human_prompts,
    tail_lines,
)
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable, iso_utc, session_key

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.security.pii import PiiConfig

__all__ = [
    "CHECKPOINT_CAP",
    "CHECKPOINT_DIR",
    "CONFIG_SCHEMA",
    "DEFAULT_MAX_PROMPTS",
    "SAID",
    "checkpoint_rel",
    "masked_excerpt",
    "precompact_checkpoint",
    "precompact_reinject",
    "select_human_prompts",
]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "max_prompts": ConfigKey("integer"),
    PII_KEY: PII_CONFIG_KEY,
}
DEFAULT_MAX_PROMPTS: Final = 10
#: Above this, re-injection would crowd the session-start context (§D.3.4).
_MAX_PROMPTS_CEILING: Final = 20
CHECKPOINT_DIR: Final = "checkpoints"
SAID: Final = "Before compaction the user said: "
_FILES: Final = "Files edited before compaction: "
_SHOWN_FILES: Final = 10
_STORED_FILES: Final = 50
#: One item, within the event's 4,000-character field next to the 600-character briefing.
CHECKPOINT_CAP: Final = LineCap(max_lines=_MAX_PROMPTS_CEILING + 1, max_chars=3_000, line_chars=260)
_EXCERPT_CHARS: Final = 200
#: Masking reads this much past the excerpt, so a value starting in the shown
#: part is always whole when the detectors see it.
_MASK_WINDOW_CHARS: Final = 1_024
_TOKEN: Final = re.compile(r"\S+")


def checkpoint_rel(session_id: str) -> str:
    """The state-root path of ``session_id``'s checkpoint (never the raw id).

    Example::

        >>> checkpoint_rel("abc")
        'checkpoints/ba7816bf8f01cfea.json'
    """
    return f"{CHECKPOINT_DIR}/{session_key(session_id)}.json"


@register_hook_handler(
    "precompact_checkpoint",
    events=["pre_compact"],
    decisions=["context", "none"],  # the hook's set (H5); pre_compact itself only observes
    config_schema=CONFIG_SCHEMA,
)
def precompact_checkpoint(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Record where the last genuine prompts are; drop the checkpoint when the transcript is odd.

    Example: ``precompact_checkpoint(pre_compact, ctx) is None`` and
    ``<state>/checkpoints/<key>.json`` holds ``{"entries": [{"uuid", "offset"}], "files": [...]}``.
    """
    store, rel = ctx.session.store, checkpoint_rel(ev.session_id)
    max_prompts = HookConfig(ctx.config, CONFIG_SCHEMA).integer(
        "max_prompts", DEFAULT_MAX_PROMPTS, minimum=1, maximum=_MAX_PROMPTS_CEILING, above="clamp"
    )
    try:
        refs = _prompt_refs(ev.transcript_path, max_prompts)
    except TranscriptShapeError:
        refs = None
    with suppress(StateUnavailable):
        if refs is None:  # an unreadable transcript must not leave an older checkpoint behind
            store.remove(rel)
        else:
            store.write_json(rel, _checkpoint(refs, _edited_files(ctx), now=ctx.clock.time()))
    return None


@register_hook_handler(
    "precompact_checkpoint:reinject",
    events=["session_start"],
    decisions=["context", "none"],
    config_schema=CONFIG_SCHEMA,
)
def precompact_reinject(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """After a compaction, the checkpointed prompts as quoted, masked, attributed lines.

    Example::

        >>> precompact_reinject(compact_start, ctx).context  # doctest: +SKIP
        ('Before compaction the user said: "do not push"',)
    """
    if ev.source != "compact" or not ev.transcript_path:
        return None
    try:
        checkpoint = ctx.session.store.read_json(checkpoint_rel(ev.session_id))
    except StateUnavailable:
        return None
    max_prompts = HookConfig(ctx.config, CONFIG_SCHEMA).integer(
        "max_prompts", DEFAULT_MAX_PROMPTS, minimum=1, maximum=_MAX_PROMPTS_CEILING, above="clamp"
    )
    refs = _refs(checkpoint)[-max_prompts:]
    try:
        prompts = read_prompts(ev.transcript_path, refs)
    except TranscriptShapeError:
        return None
    pii = pii_settings(ctx.config)
    lines = [SAID + masked_excerpt(text, pii) for text in prompts]
    lines.extend(_files_line(_strings(checkpoint.get("files"))))
    if not lines:
        return None
    text = "\n".join(clamp_lines(lines, CHECKPOINT_CAP))
    return HandlerResult(
        decision=Decision.CONTEXT, hook_id=ctx.hook.id, rule_id="checkpoint", context=(text,)
    )


def masked_excerpt(text: str, pii: PiiConfig | None) -> str:
    """``text``'s start as one quoted line: secrets (and ``pii``) masked, whitespace collapsed.

    Example::

        >>> masked_excerpt("deploy key AKIA" + "Z7Q2" * 4 + "\\nnow", None)
        '"deploy key <secret:aws-access-key-id> now"'
    """
    window = _leading_words(text, _MASK_WINDOW_CHARS)
    flat = " ".join(clean_text(_masked(window, pii)).split())
    return _quoted(flat, CHECKPOINT_CAP.line_chars - len(SAID))


def _quoted(flat: str, budget: int) -> str:
    """``flat``'s start as a JSON literal of at most ``budget`` characters, quotes intact.

    ``quote_data`` escapes non-ASCII text (``\\u00e9`` is six characters), so
    the excerpt shrinks until its literal fits: a line cap must never cut the
    closing quote off.
    """
    size = _EXCERPT_CHARS
    while True:
        quoted = quote_data(clip(flat, size), size)
        if len(quoted) <= budget or size <= 1:
            return quoted
        size = max(1, size * budget // len(quoted))


def _leading_words(text: str, limit: int) -> str:
    """Whole whitespace-separated words from ``text``'s start, about ``limit`` characters."""
    words: list[str] = []
    size = 0
    for match in _TOKEN.finditer(text):
        words.append(match.group()[: limit + _EXCERPT_CHARS])
        size += len(words[-1]) + 1
        if size >= limit:
            break
    return " ".join(words)


def _masked(text: str, pii: PiiConfig | None) -> str:
    """``text`` with every secret token and enabled PII value replaced by its category."""
    from coding_agent_playbook.security.secrets import DEFAULT_RULES

    spans = [
        (m.start(), m.end(), f"<secret:{rule.rule_id}>")
        for rule in DEFAULT_RULES
        for m in rule.regex.finditer(text)
    ]
    if pii is not None:
        from coding_agent_playbook.security.pii import scan_pii

        spans.extend((m.start, m.end, f"<pii:{m.detector}>") for m in scan_pii(text, pii))
    parts: list[str] = []
    cursor = 0
    for start, end, label in sorted(spans):
        if end <= cursor or end <= start:
            continue  # inside a span already masked
        if start >= cursor:
            parts.extend((text[cursor:start], label))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _prompt_refs(transcript_path: str | None, limit: int) -> list[EntryRef]:
    if not transcript_path:
        raise TranscriptShapeError("the event names no transcript")
    return select_human_prompts(tail_lines(transcript_path), limit=limit)


def _checkpoint(refs: Sequence[EntryRef], files: list[str], *, now: float) -> dict[str, Any]:
    return {
        "v": 1,
        "created": iso_utc(now),
        "entries": [ref.to_json() for ref in refs],
        "files": files,
    }


def _edited_files(ctx: HandlerContext) -> list[str]:
    """The repo-relative files the session wrote, oldest first; masked paths dropped."""
    if ctx.ledger is None:
        return []
    found: dict[str, None] = {}
    for line in ctx.ledger.read():
        found.update(dict.fromkeys(p for p in _strings(line.get("writes")) if p[:1] != "<"))
    return list(found)[-_STORED_FILES:]


def _files_line(files: list[str]) -> list[str]:
    if not files:
        return []
    shown = [quote_data(clean_text(path), 120) for path in files[-_SHOWN_FILES:]]
    hidden = len(files) - len(shown)
    return [_FILES + ", ".join(shown) + (f" (+{hidden} more)" if hidden else "")]


def _refs(checkpoint: Mapping[str, Any]) -> list[EntryRef]:
    rows = checkpoint.get("entries")
    found = (EntryRef.from_json(row) for row in (rows if isinstance(rows, list) else ()))
    return [ref for ref in found if ref is not None]


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
