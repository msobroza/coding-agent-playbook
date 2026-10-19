"""secret-content-guard: no secret token reaches the disk or a push (specs/prK-hook-pack.md §E.4).

Default, ``pre_tool_use``; the air-gapped gitleaks replacement. The rules are
``security.secrets``' high-precision vendor formats plus the overlay
``extra_patterns`` rendered into ``guard_config.secret_rules``:

- **Writes** (a boundary: the hook sees the exact bytes): the ``content``,
  ``new_string``, ``edits[].new_string``, ``new_source`` and ``apply_patch``
  added lines a call persists. Text over ``max_scan_bytes`` (1 MiB) is scanned
  at its head and tail and asks. Files the secret path policy covers are
  secrets-path-guard's (a new ``.env`` it lets the user approve may hold keys).
- **``git push``** (a speed bump): the added lines of the commits it would
  publish (``@{u}..HEAD``, else ``HEAD --not --remotes``).
- A token ``deny``s, naming the rule, ``<rel>:<line>`` and the match length,
  never a character of the value. ``# playbook: allow-secret <rule-id>``
  waives its line only when committed at ``HEAD`` (at the upstream, for a
  push); a new one asks, so the agent cannot authorize itself.

``on_error: ask``; a git failure on the push branch reaches the failure policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.event import ToolClass
from coding_agent_playbook.hook_runtime.handlers._secret_policy import (
    classify_path,
    content_rules,
    finding_line,
    path_policy,
)
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.security.files import user_home
from coding_agent_playbook.security.secrets import (
    MAX_SCAN_BYTES,
    PARTIAL_WINDOW_BYTES,
    SECRET_ADVICE,
    scan_added_lines,
    scan_bounded,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ContentFragment, ToolCall
    from coding_agent_playbook.hook_runtime.git.safe_git import AddedLine
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell.parse import ShellCommand
    from coding_agent_playbook.security.secrets import SecretFinding, SecretRule

__all__ = ["CONFIG_SCHEMA", "PRAGMA_ADVICE", "secret_content_guard"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "extra_patterns": ConfigKey("regex", "extend"),
    "max_scan_bytes": ConfigKey("integer"),
}
PRAGMA_ADVICE: Final = (
    "Only a pragma already committed at HEAD waives a finding; ask the user to confirm."
)
_UNPARSED_PUSH: Final = re.compile(r"\bgit\b[^;&|\n]*\bpush\b")
_OLD_FOR: Final = {"new_string": "old_string", "newString": "oldString"}
_EDIT_FIELD: Final = re.compile(r"^edits\[(\d+)\]\.new_string$")

type Verdict = Literal["deny", "ask", "pass"]


@dataclass(frozen=True, slots=True)
class _Judged:
    """One finding and the guard's verdict on it."""

    finding: SecretFinding
    verdict: Verdict


@dataclass(slots=True)
class _Scan:
    """Everything one call would persist or publish, judged."""

    judged: list[_Judged] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)
    push: bool = False


@register_hook_handler(
    "secret_content_guard",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "none"],
    config_schema=CONFIG_SCHEMA,
)
def secret_content_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny a write or push carrying a secret token; ask on a new pragma or a partial scan.

    Example::

        >>> secret_content_guard(write_with_aws_key, ctx).reason.splitlines()[0]
        ... # doctest: +SKIP
        'Blocked: this write adds a secret token at "config.py":2 aws-access-key-id (20 chars).'
    """
    tool = ev.tool
    if tool is None or ev.repo is None:
        return None
    rules = content_rules(ctx.cfg)
    if tool.tool_class is ToolClass.SHELL:
        scan = _push_scan(tool.command, ctx, rules)
    else:
        scan = _write_scan(tool, ctx, rules)
    return _result(scan, ctx)


# --- writes ---------------------------------------------------------------------------------


def _write_scan(tool: ToolCall, ctx: HandlerContext, rules: Sequence[SecretRule]) -> _Scan:
    cap = HookConfig(ctx.config, CONFIG_SCHEMA).integer("max_scan_bytes", MAX_SCAN_BYTES, minimum=1)
    window = min(PARTIAL_WINDOW_BYTES, cap // 2)
    by_raw = {path.raw: path for path in tool.write_paths}
    secret = _secret_path_test(ctx)
    scan = _Scan()
    for fragment in tool.content:
        path = by_raw.get(fragment.path)
        if path is not None and secret(path):
            continue  # secrets-path-guard owns credential files
        rel = fragment.path if path is None else (path.repo_rel or path.path)
        found = scan_bounded(fragment.text, rel, rules=rules, max_bytes=cap, window=window)
        if found.partial:
            scan.partial.append(rel)
        first = _first_line(tool, fragment, path) if found.findings else 0
        scan.judged.extend(
            _Judged(_located(f, first), _write_verdict(f, fragment.text, rel, ctx))
            for f in found.findings
        )
    return scan


def _write_verdict(finding: SecretFinding, text: str, rel: str, ctx: HandlerContext) -> Verdict:
    if not finding.pragma:
        return "deny"
    from coding_agent_playbook.hook_runtime.escape import pragma_at_head

    line = _line(text, finding.line)
    return "pass" if line and pragma_at_head(ctx.git, rel, line) else "ask"


def _first_line(tool: ToolCall, fragment: ContentFragment, path: NormalizedPath | None) -> int:
    """The file line ``fragment``'s first line lands on: 1 for ``content``, 0 when unknown.

    An Edit's ``new_string`` replaces its ``old_string``, found in the current file.
    """
    if fragment.field == "content":
        return 1
    old = _old_string(tool.raw_input, fragment.field)
    if old is None or path is None:
        return 0
    try:
        with open(path.realpath, encoding="utf-8", errors="replace") as handle:
            current = handle.read(MAX_SCAN_BYTES)
    except OSError:
        return 0
    at = current.find(old)
    return 0 if at < 0 else current.count("\n", 0, at) + 1


def _old_string(raw: Mapping[str, object], field_name: str) -> str | None:
    key = _OLD_FOR.get(field_name)
    if key is not None:
        value = raw.get(key)
        return value if isinstance(value, str) and value else None
    match = _EDIT_FIELD.match(field_name)
    edits = raw.get("edits")
    if match is None or not isinstance(edits, list) or int(match[1]) >= len(edits):
        return None
    edit = edits[int(match[1])]
    old = edit.get("old_string") if isinstance(edit, dict) else None
    return old if isinstance(old, str) and old else None


def _located(finding: SecretFinding, first: int) -> SecretFinding:
    """``finding`` at its file line (fragment line + offset), or path-only when unknown."""
    line = first + finding.line - 1 if first and finding.line else 0
    return replace(finding, line=line)


def _secret_path_test(ctx: HandlerContext) -> Callable[[NormalizedPath], bool]:
    """Whether a written path is a credential file (secrets-path-guard's to judge)."""
    policy, home = path_policy(ctx.cfg), ctx.home or user_home()

    def secret(path: NormalizedPath) -> bool:
        verdict = classify_path(policy, path, home=home, platform=ctx.platform)
        return verdict in ("deny", "ask")

    return secret


# --- git push -------------------------------------------------------------------------------


def _push_scan(
    command: ShellCommand | None, ctx: HandlerContext, rules: Sequence[SecretRule]
) -> _Scan:
    if command is None or not _pushes(command):
        return _Scan()
    git = ctx.git
    upstream = git.upstream()
    policy, home = path_policy(ctx.cfg), ctx.home or user_home()
    added = [
        line
        for line in git.unpushed_lines(upstream).added
        if not policy.matches(line.path, home=home, platform=ctx.platform)
    ]
    cap = HookConfig(ctx.config, CONFIG_SCHEMA).integer("max_scan_bytes", MAX_SCAN_BYTES, minimum=1)
    kept, partial = _within(added, cap)
    texts = {(line.path, line.line): line.text for line in kept}
    scan = _Scan(partial=["the unpushed commits"] if partial else [], push=True)
    for finding in scan_added_lines(kept, rules=rules):
        text = texts.get((finding.path, finding.line), "")
        scan.judged.append(_Judged(finding, _push_verdict(finding, text, upstream, ctx)))
    return scan


def _pushes(command: ShellCommand) -> bool:
    """Whether a segment runs ``git push`` (any ``git`` token text, when the parse failed)."""
    if command.parse_error is not None:
        return _UNPARSED_PUSH.search(command.text) is not None
    from coding_agent_playbook.hook_runtime.shell.git_command import parse_git

    for segment in command.segments:
        invocation = parse_git(segment) if segment.argv[:1] in (("git",), ("git.exe",)) else None
        if invocation is not None and invocation.subcommand == "push":
            return True
    return False


def _push_verdict(
    finding: SecretFinding, text: str, upstream: str | None, ctx: HandlerContext
) -> Verdict:
    """A pragma counts only on a line the upstream already has (no upstream: never)."""
    if not finding.pragma:
        return "deny"
    if upstream is None or not text.strip():
        return "ask"
    blob = ctx.git.show(upstream, finding.path)
    lines = () if blob is None else blob.decode("utf-8", "replace").splitlines()
    return "pass" if text.strip() in {line.strip() for line in lines} else "ask"


def _within(lines: list[AddedLine], cap: int) -> tuple[list[AddedLine], bool]:
    """The leading ``lines`` whose text fits ``cap`` bytes, and whether any was left out."""
    total = 0
    for index, line in enumerate(lines):
        total += len(line.text) + 1
        if total > cap:
            return lines[:index], True
    return lines, False


# --- the result -----------------------------------------------------------------------------


def _result(scan: _Scan, ctx: HandlerContext) -> HandlerResult | None:
    hook_id = ctx.hook.id
    denied = [j.finding for j in scan.judged if j.verdict == "deny"]
    if denied:
        more = f" (and {len(denied) - 1} more)" if len(denied) > 1 else ""
        where = "an unpushed commit adds" if scan.push else "this write adds"
        head = f"Blocked: {where} a secret token at {finding_line(denied[0])}{more}."
        return HandlerResult(
            decision=Decision.DENY,
            hook_id=hook_id,
            rule_id=denied[0].rule_id,
            reason=f"{head}\n{SECRET_ADVICE}",
        )
    asked = [j.finding for j in scan.judged if j.verdict == "ask"]
    if asked:
        head = f"{finding_line(asked[0])} carries a new allow-secret pragma."
        return HandlerResult(
            decision=Decision.ASK,
            hook_id=hook_id,
            rule_id="new_allow_secret_pragma",
            reason=f"{head}\n{PRAGMA_ADVICE}",
        )
    if scan.partial:
        head = f"{quote_data(scan.partial[0])} is too large to scan whole: only its head and tail were."
        return HandlerResult(
            decision=Decision.ASK,
            hook_id=hook_id,
            rule_id="partially_scanned",
            reason=f"{head}\nConfirm with the user that it holds no secret.",
        )
    return None


def _line(text: str, number: int) -> str:
    lines = text.splitlines()
    return lines[number - 1] if 0 < number <= len(lines) else ""
