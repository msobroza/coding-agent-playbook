"""local-audit-log's line: the structure of an event, never its content (specs/prK-hook-pack.md §E.5).

Free-form command text cannot be redacted reliably (``mysql -pS3cret``, ``curl
-u user:pass``), so by default a shell call is recorded as **structure only**:
per segment the argv0 basename, a subcommand for the known multi-command tools
and the flag NAMES (``-pS3cret`` -> ``-p``, ``--password=x`` -> ``--password``),
never a value or a positional argument. Paths are repo-relative, a secret path
is ``<secret-path>`` and one outside the repository ``<outside>`` (the ledger's
masks). A prompt is its length, sha256 and secret-category counts, plus PII
category counts when an overlay enabled PII (``security.pii``, never a value).
``config.full_commands`` adds :func:`redacted_text`, the best-effort redaction
an org opts into knowing its limits. Every string that is not a closed-set value
is shape-checked, so an odd argv0 becomes ``<other>`` rather than a leak.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.state.audit_log import encode_jsonl_line
from coding_agent_playbook.hook_runtime.state.ledger import mask_path
from coding_agent_playbook.hook_runtime.state.store import iso_utc

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.globs import GlobSet
    from coding_agent_playbook.hook_runtime.shell.segments import Segment
    from coding_agent_playbook.security.pii import PiiConfig

__all__ = [
    "OTHER",
    "SUBCOMMAND_TOOLS",
    "activity_record",
    "command_structure",
    "fitted",
    "flag_name",
    "prompt_summary",
    "redacted_text",
]

OTHER: Final = "<other>"
REDACTED: Final = "<redacted>"
#: Tools whose first argument is a subcommand verb (``git push``), not a value (``mysql db``).
SUBCOMMAND_TOOLS: Final = frozenset(
    {
        "apt",
        "apt-get",
        "brew",
        "cargo",
        "conda",
        "docker",
        "gh",
        "git",
        "go",
        "helm",
        "kubectl",
        "npm",
        "pdm",
        "pip",
        "pip3",
        "playbook",
        "playbook-hook",
        "pnpm",
        "poetry",
        "podman",
        "pre-commit",
        "ruff",
        "terraform",
        "uv",
        "yarn",
    }
)
#: Flags whose next word is a credential in the redacted full text.
_SECRET_FLAGS: Final = frozenset(
    {"-p", "-P", "-u", "-H", "--password", "--pass", "--user", "--header", "--token", "--auth"}
)
_WORD: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")
_TOOL_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_SUBCOMMAND: Final = re.compile(r"[a-z][a-z0-9-]{0,31}")
_FLAG: Final = re.compile(r"--?[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
_USERINFO: Final = re.compile(r"(?<=://)[^/@\s]+@")
_MAX_SEGMENTS: Final = 8
_MAX_FLAGS: Final = 8
_MAX_PATHS: Final = 8
_MAX_TEXT: Final = 1024
_PREV_PLACEHOLDER: Final = "0" * 64


def activity_record(
    ev: CanonicalEvent,
    *,
    now: float,
    secret: GlobSet,
    platform: str,
    full_commands: bool = False,
    pii: PiiConfig | None = None,
) -> dict[str, Any]:
    """The local-audit-log line for ``ev`` (``state.audit_log.ACTIVITY_RECORD_KEYS`` only).

    ``pii`` (the overlay-enabled detectors, else ``None``) adds a prompt's PII
    category counts.

    Example::

        >>> activity_record(post_bash, now=clock.time(), secret=cfg.secret_paths,
        ...                 platform="linux")["commands"]  # doctest: +SKIP
        [{'argv0': 'mysql', 'flags': ['-p'], 'sub': None}]
    """
    record: dict[str, Any] = {
        "v": 1,
        "ts": iso_utc(now),
        "harness": ev.harness.value,
        "session_id": ev.session_id,
        "event": ev.name.value,
    }
    if ev.name is EventName.SESSION_START:
        record["source"] = _shaped(ev.source, _SUBCOMMAND)
    if ev.name is EventName.USER_PROMPT_SUBMIT and ev.prompt is not None:
        record["prompt"] = prompt_summary(ev.prompt, pii=pii)
    if ev.tool is not None:
        record.update(_tool_fields(ev.tool, secret, platform, full_commands))
    return record


def _tool_fields(
    tool: ToolCall, secret: GlobSet, platform: str, full_commands: bool
) -> dict[str, Any]:
    paths = dict.fromkeys(
        mask_path(p, secret, platform=platform) for p in (*tool.paths, *tool.write_paths)
    )
    fields: dict[str, Any] = {
        "tool_name": _shaped(tool.name, _TOOL_NAME),
        "tool_class": tool.tool_class.value,
        "paths": list(paths)[:_MAX_PATHS],
        "duration_ms": None,  # neither harness payload carries a duration today
    }
    if tool.response is not None:
        fields.update(
            ok=tool.response.ok,
            exit_code=tool.response.exit_code,
            interrupted=tool.response.is_interrupt,
        )
    command = tool.command
    if command is not None:
        segments = command.segments[:_MAX_SEGMENTS]
        fields["commands"] = [command_structure(s.argv) for s in segments if s.argv]
        if full_commands:
            fields["command_text"] = redacted_text(segments)
    return fields


def command_structure(argv: Sequence[str]) -> dict[str, Any]:
    """One segment as ``{argv0, sub, flags}``: names only, never values or positionals.

    Example::

        >>> command_structure(["mysql", "-pS3cret", "db"])
        {'argv0': 'mysql', 'sub': None, 'flags': ['-p']}
    """
    argv0 = _shaped(posixpath.basename(argv[0]), _WORD) if argv else OTHER
    sub = None
    if argv0 in SUBCOMMAND_TOOLS and len(argv) > 1 and _SUBCOMMAND.fullmatch(argv[1]):
        sub = argv[1]
    flags: list[str] = []
    for arg in argv[1:]:
        if arg == "--":
            break  # everything after is positional
        name = flag_name(arg)
        if name is not None and name not in flags:
            flags.append(name)
    return {"argv0": argv0, "sub": sub, "flags": flags[:_MAX_FLAGS]}


def flag_name(arg: str) -> str | None:
    """The NAME of a flag argument (short flags cut to one letter, long ones at ``=``), else None.

    Example::

        >>> flag_name("-pS3cret"), flag_name("--password=x"), flag_name("db")
        ('-p', '--password', None)
    """
    if not arg.startswith("-") or arg in ("-", "--"):
        return None
    name = arg.split("=", 1)[0] if arg.startswith("--") else arg[:2]
    return name if _FLAG.fullmatch(name) else None


def prompt_summary(prompt: str, *, pii: PiiConfig | None = None) -> dict[str, Any]:
    """A prompt as its length, sha256 and secret-rule counts; never a character of it.

    With ``pii``, also its PII category counts (``{"iban": 1}``).

    Example::

        >>> prompt_summary("hi")["length"]
        2
    """
    from coding_agent_playbook.security.secrets import scan_bounded

    counts: dict[str, int] = {}
    for finding in scan_bounded(prompt, "<prompt>").findings:
        counts[finding.rule_id] = counts.get(finding.rule_id, 0) + 1
    digest = hashlib.sha256(prompt.encode("utf-8", "surrogatepass")).hexdigest()
    summary = {"length": len(prompt), "sha256": digest, "secrets": dict(sorted(counts.items()))}
    if pii is not None:
        from coding_agent_playbook.security.pii import category_counts, scan_pii

        summary["pii"] = category_counts(scan_pii(prompt, pii))
    return summary


def redacted_text(segments: Iterable[Segment]) -> str:
    """The segments' words with flag values, credentials and secret tokens replaced.

    Best effort, so only behind ``config.full_commands``: env assignments,
    ``--k=v`` and attached ``-pVALUE`` values, the word after a credential
    flag, URL userinfo and every secret-rule match become ``<redacted>``.

    Example::

        >>> redacted_text(parse_shell("mysql -pS3cret db", "posix", None).segments)  # doctest: +SKIP
        'mysql -p<redacted> db'
    """
    from coding_agent_playbook.security.secrets import DEFAULT_RULES

    parts: list[str] = []
    for segment in segments:
        words = [f"{name}={REDACTED}" for name, _ in segment.env]
        words.extend(_redacted_words(segment.argv))
        parts.append(" ".join(words))
    text = " ; ".join(parts)
    for rule in DEFAULT_RULES:
        text = rule.regex.sub(REDACTED, text)
    return text[:_MAX_TEXT]


def _redacted_words(argv: Sequence[str]) -> list[str]:
    words: list[str] = []
    secret_next = False
    for arg in argv:
        if secret_next:
            words.append(REDACTED)
            secret_next = False
            continue
        words.append(_redacted_word(arg))
        secret_next = arg in _SECRET_FLAGS
    return words


def _redacted_word(arg: str) -> str:
    if arg.startswith("--") and "=" in arg:
        return f"{arg.split('=', 1)[0]}={REDACTED}"
    if len(arg) > 2 and arg.startswith("-") and arg[1].isalpha() and not arg.startswith("--"):
        return f"{arg[:2]}{REDACTED}"
    return _USERINFO.sub(f"{REDACTED}@", arg)


def fitted(record: dict[str, Any]) -> dict[str, Any]:
    """``record`` trimmed until it encodes as one line within the 4 KiB atomic-write limit.

    Drops ``command_text`` first, then halves ``paths`` and ``commands``.

    Example: ``len(encode_jsonl_line(fitted(record))) <= 4096``.
    """
    current = dict(record)
    while not _fits(current):
        if "command_text" in current:
            del current["command_text"]
            continue
        longest = max(("paths", "commands"), key=lambda key: len(current.get(key) or ()))
        items = current.get(longest) or []
        if not items:
            raise ValueError(f"activity record does not fit one line: keys {sorted(current)}")
        current[longest] = items[: len(items) // 2]
    return current


def _fits(record: dict[str, Any]) -> bool:
    try:
        # Room for the chain's ``prev`` digest, which append_activity adds when chaining.
        encode_jsonl_line({**record, "prev": _PREV_PLACEHOLDER})
    except ValueError:
        return False
    return True


def _shaped(value: str | None, shape: re.Pattern[str]) -> str | None:
    """``value`` when it has ``shape`` (a name, never free text), else ``<other>``; None stays None."""
    if value is None:
        return None
    return value if shape.fullmatch(value) else OTHER
