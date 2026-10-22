"""document-layout-guard: specs and plans go to the document layout (prU D60, D61, D71).

Default tier, ``pre_tool_use``. A spec-driven framework writes its specs and plans
where its own text says (``docs/superpowers/plans/``, ``.scratch/<slug>/spec.md``);
the repo keeps them in one layout whatever the framework (D60). The guard denies a
write that lands in a known other location and names the directory it belongs in:

- anything under a ``blocked_dirs`` entry (a framework's own folder, by default
  ``docs/superpowers``);
- a spec or plan file (``spec.md``, ``*-design.md``, ``plan.md``, anything under an
  ``issues/`` or ``tickets/`` folder) under ``scratch_dir``, which holds only
  throwaway prototypes.

A write inside the configured ``specs_dir`` or ``plans_dir`` always passes, even
when that directory lies inside a blocked one. The directories are the handler
config's D60 defaults; ``playbook sync``'s layout adapter rewrites them in
``guard_config.json`` to the repo's ``[layout]`` (D71, D78(12)), so a repo with
``specs = "specs"`` gets ``specs`` here. Not guard-class (``on_error: open``): a
misplaced document is moved, not leaked.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.artifacts.path_globs import fold_key
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.config.keys import ConfigKey
from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.registry import register_hook_handler
from coding_agent_playbook.hook_runtime.handlers._shared.targets import (
    file_write_paths,
    shell_write_targets,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext

__all__ = ["CONFIG_SCHEMA", "DEFAULT_DIRS", "document_layout_guard"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "specs_dir": ConfigKey("string"),
    "plans_dir": ConfigKey("string"),
    "scratch_dir": ConfigKey("string"),
    "blocked_dirs": ConfigKey("list", "extend"),
}

#: The D60 defaults a missing or blank key falls back to. The hook runtime imports only
#: stdlib leaves, so this mirrors ``config.layout.LAYOUT_DEFAULTS`` (a test pins the two).
DEFAULT_DIRS: Final[Mapping[str, str]] = MappingProxyType(
    {"specs_dir": "docs/specs", "plans_dir": "docs/plans", "scratch_dir": ".scratch"}
)

#: What a misplaced document is: a spec, a plan, or (in a blocked folder) unknown.
type DocumentKind = Literal["spec", "plan", "document"]

_PLAN_FOLDERS: Final = frozenset({"plans", "plan", "issues", "tickets"})
_SPEC_FOLDERS: Final = frozenset({"specs", "spec"})
_PLAN_WORDS: Final = frozenset({"plan", "plans", "tickets", "issues"})
_SPEC_WORDS: Final = frozenset({"spec", "specs", "prd", "design"})
_WORD_SPLIT: Final = re.compile(r"[-_.\s]+")
_PATH_CHARS: Final = 80


@dataclass(frozen=True, slots=True)
class _Layout:
    """The handler config's directories, folded like path keys on darwin and win32."""

    specs: str
    plans: str
    scratch: str
    blocked: tuple[str, ...]


@register_hook_handler(
    "document_layout_guard",
    events=["pre_tool_use"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
)
def document_layout_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny a spec or plan written outside the document layout; ``None`` (pass) otherwise.

    Example::

        >>> document_layout_guard(write_superpowers_plan, ctx).reason  # doctest: +SKIP
        '"docs/superpowers/plans/x.md" is a plan outside the document layout. Write it ...'
    """
    if ev.tool is None or ev.repo is None:
        return None
    raw = _layout(ctx.config)
    folded = _fold(raw, ctx.platform)
    for path in _targets(ev, ctx):
        if path.repo_rel is None or path.sibling_worktree:
            continue
        kind = misplaced_kind(fold_key(path.repo_rel, ctx.platform), folded)
        if kind is not None:
            return _deny(ctx, path.repo_rel, kind, raw)
    return None


def misplaced_kind(rel: str, layout: _Layout) -> DocumentKind | None:
    """What ``rel`` (repo-relative, POSIX) is when it lies outside the layout, else ``None``.

    Example::

        >>> misplaced_kind("docs/superpowers/plans/x.md", _layout({}))
        'plan'
    """
    if _under(rel, layout.specs) or _under(rel, layout.plans):
        return None
    if any(_under(rel, blocked) for blocked in layout.blocked):
        return document_kind(rel) or "document"
    if _under(rel, layout.scratch) and rel.endswith(".md"):
        return document_kind(rel)
    return None


def document_kind(rel: str) -> Literal["spec", "plan"] | None:
    """Whether ``rel`` names a spec or a plan, by its folders first, then its file name.

    Example::

        >>> document_kind(".scratch/feature/issues/01-login.md"), document_kind("a/spec.md")
        ('plan', 'spec')
    """
    folders = set(rel.split("/")[:-1])
    if folders & _PLAN_FOLDERS:
        return "plan"
    if folders & _SPEC_FOLDERS:
        return "spec"
    words = set(_WORD_SPLIT.split(posixpath.splitext(posixpath.basename(rel))[0]))
    if words & _PLAN_WORDS:
        return "plan"
    if words & _SPEC_WORDS:
        return "spec"
    return None


def _targets(ev: CanonicalEvent, ctx: HandlerContext) -> list[NormalizedPath]:
    """File-tool write paths, then each Bash segment's write targets."""
    from coding_agent_playbook.hook_runtime.shell.parse import write_targets  # Bash branch only

    assert ev.tool is not None  # checked by the handler
    return [*file_write_paths(ev.tool), *shell_write_targets(ev, ctx, write_targets)]


def _layout(raw: Mapping[str, object]) -> _Layout:
    """The configured directories; a missing, malformed or blank key keeps its D60 default."""
    config = HookConfig(raw, CONFIG_SCHEMA)

    def directory(key: str) -> str:
        default = DEFAULT_DIRS[key]
        return _bare(config.choice(key, default)) or default

    rows = (_bare(row) for row in config.strings("blocked_dirs", blanks="drop_blank"))
    return _Layout(
        specs=directory("specs_dir"),
        plans=directory("plans_dir"),
        scratch=directory("scratch_dir"),
        blocked=tuple(row for row in rows if row),
    )


def _bare(directory: str) -> str:
    """``directory`` without surrounding blanks or slashes (``" docs/plans/ "`` -> ``docs/plans``)."""
    return directory.strip().strip("/")


def _fold(layout: _Layout, platform: str) -> _Layout:
    return _Layout(
        specs=fold_key(layout.specs, platform),
        plans=fold_key(layout.plans, platform),
        scratch=fold_key(layout.scratch, platform),
        blocked=tuple(fold_key(row, platform) for row in layout.blocked),
    )


def _under(rel: str, directory: str) -> bool:
    return rel.startswith(f"{directory}/")


def _deny(ctx: HandlerContext, rel: str, kind: DocumentKind, layout: _Layout) -> HandlerResult:
    """The deny: the path and what it is, then the directory it belongs in."""
    where = {
        "spec": f"Write specs to {layout.specs}/YYYY-MM-DD-<slug>.md.",
        "plan": f"Write plans to {layout.plans}/YYYY-MM-DD-<slug>.md.",
        "document": f"Write specs to {layout.specs}/ and plans to {layout.plans}/.",
    }[kind]
    head = f"{quote_data(rel, _PATH_CHARS)} is a {kind} outside the document layout."
    return HandlerResult(
        decision=Decision.DENY,
        hook_id=ctx.hook.id,
        rule_id="misplaced_document",
        reason=f"{head}\n{where}",
    )
