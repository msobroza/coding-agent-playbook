"""validate-then-sync-on-canonical-edit: report validate failures in-turn (specs/prK-hook-pack.md §E.1).

After an Edit or Write of a canonical source (``playbook/{rules,prompts,
skills,hooks}/**``, ``.coding-agent-playbook.toml``, an overlay checkout's
``src/*/resources/...``, or the engine checkout's catalog
``catalog/core/...`` and ``catalog/plugins/*/...``), it runs ``playbook validate`` as a child
process and returns the ``FAIL`` lines that name the edited file or its id
(the cross-references the edit broke included), at most 15, as context:
``resolve before finishing``. Context, never a block: a prompt written before
the rule it includes is a normal transient state; the ``drift`` Stop stage is
the hard gate.

With ``[hooks] auto_sync`` (``guard_config.auto_sync``) and a clean validate
it runs ``playbook sync`` too, except after an edit of ``playbook/hooks/**``,
a checkout's ``src/*/resources/hooks/**``, the engine's ``catalog/core/hooks/**``
or a bundled plugin's ``catalog/plugins/*/hooks/**``, ``.coding-agent-playbook.toml`` or a hook
artifact: the runtime cannot tell which keys a config edit touched, so this
conservative superset covers ``[hooks]``, ``overlays_enabled`` and
``adapters_enabled``. Then it says ``ask the user to run playbook sync``.

Quality class: a child that times out fails open with one note per session.
Two edits within 2 s run one validate (the shared source-changed debounce).
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.proc import ProcTimeout
from coding_agent_playbook.hook_runtime.dispatch.registry import register_hook_handler
from coding_agent_playbook.hook_runtime.globs import compile_globs
from coding_agent_playbook.hook_runtime.handlers._source_changed import (
    DEBOUNCE_S,
    context_result,
    fail_lines,
    run_playbook,
    timed_out,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext

__all__ = ["CANONICAL_GLOBS", "NO_AUTO_SYNC_GLOBS", "validate_then_sync_on_canonical_edit"]

_KINDS: Final = ("rules", "prompts", "skills", "hooks")
#: The engine checkout's own layers: its catalog, which left
#: ``src/coding_agent_playbook/resources/`` in SPEC v0.19 (as ``content/``, now ``catalog/``).
_CATALOG_LAYERS: Final = ("catalog/core", "catalog/plugins/*")
#: The canonical sources; ``HOOK.md``'s matcher lists the same globs (a test pins them).
CANONICAL_GLOBS: Final[tuple[str, ...]] = (
    *(f"playbook/{kind}/**" for kind in _KINDS),
    ".coding-agent-playbook.toml",
    *(f"src/*/resources/{kind}/**" for kind in _KINDS),
    *(f"{layer}/{kind}/**" for layer in _CATALOG_LAYERS for kind in _KINDS),
)
#: Edits after which auto-sync never runs: hook sources and the config (§E.1).
NO_AUTO_SYNC_GLOBS: Final[tuple[str, ...]] = (
    "playbook/hooks/**",
    "src/*/resources/hooks/**",
    *(f"{layer}/hooks/**" for layer in _CATALOG_LAYERS),
    ".coding-agent-playbook.toml",
)
_ADVICE: Final = "ask the user to run playbook sync"
_RESOLVE: Final = "resolve before finishing:"
_FRONTMATTER_ID: Final = re.compile(r"^id:\s*['\"]?([\w.-]+)", re.MULTILINE)
_HEAD_BYTES: Final = 8192
_PATH_CHARS: Final = 120


@register_hook_handler(
    "validate_then_sync_on_canonical_edit",
    events=["post_tool_use"],
    decisions=["context", "none"],
)
def validate_then_sync_on_canonical_edit(
    ev: CanonicalEvent, ctx: HandlerContext
) -> HandlerResult | None:
    """Context naming the validate failures of an edited canonical source; ``None`` when clean.

    Example::

        >>> validate_then_sync_on_canonical_edit(write_of_broken_rule, ctx).context[0]
        ... # doctest: +SKIP
        'playbook validate fails for "playbook/rules/glossary.md"; resolve before finishing:\\n...'
    """
    edited = _canonical_edits(ev, ctx)
    if not edited or ev.repo is None or not ctx.session.debounce(ctx.hook.id, DEBOUNCE_S):
        return None
    root = ev.repo.worktree_root
    try:
        validated = run_playbook(ctx, root, ["validate"])
    except ProcTimeout:
        validated = None
    if validated is None:
        return timed_out(ctx, "playbook validate")
    if not validated.ok:
        return _failures(ctx, edited, validated.stdout)
    if not ctx.cfg.tables.auto_sync():
        return None
    return _auto_sync(ctx, root, edited)


def _canonical_edits(ev: CanonicalEvent, ctx: HandlerContext) -> list[NormalizedPath]:
    """The in-repo paths the tool wrote that are canonical sources."""
    if ev.tool is None:
        return []
    canonical = compile_globs(CANONICAL_GLOBS, platform=ctx.platform)
    return [p for p in ev.tool.write_paths if p.repo_rel is not None and canonical.matches(p.key)]


def _failures(
    ctx: HandlerContext, edited: Sequence[NormalizedPath], output: bytes
) -> HandlerResult | None:
    """The FAIL lines about ``edited``; else, under auto-sync, why sync did not run."""
    paths = [p.repo_rel or "" for p in edited]
    lines = fail_lines(output, paths=paths, ids=[i for p in edited for i in _ids_of(p)])
    if lines:
        head = f"playbook validate fails for {_quoted(paths)}; {_RESOLVE}"
        return context_result(ctx, "\n".join([head, *lines]), "validate")
    if not ctx.cfg.tables.auto_sync():
        return None
    return context_result(
        ctx, f"playbook validate fails elsewhere, so playbook sync was not run; {_ADVICE}.", "sync"
    )


def _auto_sync(
    ctx: HandlerContext, root: str, edited: Sequence[NormalizedPath]
) -> HandlerResult | None:
    """Run ``playbook sync`` unless an edit is a hook source, the config or a hook artifact."""
    if any(_never_auto_sync(ctx, p) for p in edited):
        reason = "[hooks] auto_sync never syncs hook or config edits"
        return context_result(ctx, f"{reason}; {_ADVICE}.", "sync")
    try:
        synced = run_playbook(ctx, root, ["sync"])
    except ProcTimeout:
        synced = None
    if synced is None:
        return timed_out(ctx, "playbook sync")
    if synced.ok:
        return None
    return context_result(
        ctx, f"playbook sync failed (exit {synced.returncode}); {_ADVICE}.", "sync"
    )


def _never_auto_sync(ctx: HandlerContext, path: NormalizedPath) -> bool:
    globs = [*NO_AUTO_SYNC_GLOBS, *ctx.cfg.tables.protected().hook_artifacts]
    return compile_globs(globs, platform=ctx.platform).matches(path.key)


def _ids_of(path: NormalizedPath) -> list[str]:
    """The artifact ids an edit may break: its frontmatter id, file stem and owning dir."""
    rel = path.repo_rel or ""
    name = posixpath.basename(rel)
    found = [_frontmatter_id(path.path), name.split(".", 1)[0]]
    parts = rel.split("/")
    for kind in ("skills", "hooks"):
        if kind in parts[:-1]:
            found.append(posixpath.basename(posixpath.dirname(rel)))
    return [i for i in dict.fromkeys(found) if i]


def _frontmatter_id(path: str) -> str:
    """The ``id:`` of a markdown file's head, or ``""`` (unreadable, absent)."""
    if not path.endswith((".md", ".j2")):
        return ""
    try:
        with open(path, "rb") as handle:
            head = handle.read(_HEAD_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return ""
    match = _FRONTMATTER_ID.search(head) if head.startswith("---") else None
    return match.group(1) if match else ""


def _quoted(paths: Sequence[str]) -> str:
    return ", ".join(quote_data(p, _PATH_CHARS) for p in dict.fromkeys(paths))
