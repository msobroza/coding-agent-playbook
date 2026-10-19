"""The value types sync hands the guard_config writer (specs/prK-hook-pack.md §E.0.5, §E.1).

- :class:`DetectInputs`: the detector facts and the :class:`ApplicabilityRow`
  rows the ``facts`` and ``applicability`` tables render (``_tables_detect``).
  :func:`applicability_rows` builds the rows: ``{kind, id, applies_if, source,
  active}`` for every merged rule and prompt and every hook that only
  applicability keeps off. ``applies_if`` is a list of predicates that must all
  hold (a hook's own, then its linked rule's; ``[]`` = always) and ``active``
  whether they held at this sync, so resync-on-detector-input-change can name
  what a fact change turns on or off without rebuilding a ``SyncContext``
  (``validation.context`` imports yaml);
- :class:`ProtectInputs`: the written set as :class:`ProtectedRow` lock rows,
  the adapters' scan dirs and the layer packages the ``protected`` table
  renders (``_tables_protect``); sync assembles them (``sync._protect``).

All of it depends only on the repository (``detect()`` and ``has_file`` read the
repo, never the machine), so ``sync --check`` byte-compares what it renders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, cast

from coding_agent_playbook.hooks.resolution.effective import effective_applies_if
from coding_agent_playbook.hooks.resolution.resolved import APPLICABILITY_GATES

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook, SkippedHook

__all__ = [
    "ApplicabilityRow",
    "DetectInputs",
    "HookView",
    "ProtectInputs",
    "ProtectedRow",
    "applicability_rows",
]


class HookView(Protocol):
    """An effective hook view: ``hooks.resolution.resolved.EffectiveHooks`` or the sync's ``SyncHooks``."""

    @property
    def resolved(self) -> Sequence[ResolvedHook]: ...

    @property
    def skipped(self) -> Sequence[SkippedHook]: ...


@dataclass(frozen=True)
class ApplicabilityRow:
    """One ``applicability`` row; ``applies_if`` predicates must all hold.

    Example::

        >>> ApplicabilityRow("rule", "ml", ({"any_ml_stack": ["torch"]},), "pkg", False).to_json()
        ... # doctest: +SKIP
        {'kind': 'rule', 'id': 'ml', 'applies_if': [{'any_ml_stack': ['torch']}], ...}
    """

    kind: str
    id: str
    applies_if: tuple[Mapping[str, Any], ...]
    source: str
    active: bool

    def to_json(self) -> dict[str, Any]:
        """The rendered row (predicates deep-copied as plain dicts)."""
        return {
            "kind": self.kind,
            "id": self.id,
            "applies_if": [_plain(predicate) for predicate in self.applies_if],
            "source": self.source,
            "active": self.active,
        }


@dataclass(frozen=True)
class DetectInputs:
    """What ``facts`` and ``applicability`` are rendered from: detector facts and the rows.

    Example: ``DetectInputs(facts=ctx.facts, applicability=applicability_rows(...))``.
    """

    facts: Mapping[str, Any] = field(default_factory=dict)
    applicability: Sequence[ApplicabilityRow] = ()


def applicability_rows(
    *,
    rules: Sequence[Rule],
    prompts: Sequence[Prompt],
    hooks: Sequence[Hook],
    view: HookView,
    facts: Mapping[str, Any],
    repo_root: Path,
) -> list[ApplicabilityRow]:
    """Rows for every merged rule and prompt, and each hook only applicability keeps off.

    ``rules``/``prompts``/``hooks`` are the merged, pre-``applies_if`` sets
    (``SyncContext.*_resolved``) and ``view`` their effective hook view. A hook
    off for another reason (tier, ``disable``, no adapter) gets no row: no fact
    change can turn it on. An invalid predicate counts as not holding
    (validate gates sync on it first).

    Example::

        rows = applicability_rows(rules=ctx.rules_resolved, prompts=ctx.prompts_resolved,
                                  hooks=ctx.hooks_resolved, view=view, facts=ctx.facts,
                                  repo_root=ctx.repo_root)
    """
    rows = [
        _artifact_row(kind, artifact, facts, repo_root)
        for kind, group in (("rule", rules), ("prompt", prompts))
        for artifact in group
    ]
    by_id = {rule.frontmatter.id: rule for rule in rules}
    on = {hook.id for hook in view.resolved}
    gated = {skip.id for skip in view.skipped if skip.gate in APPLICABILITY_GATES}
    for hook in hooks:
        hook_id = hook.frontmatter.id
        predicates = effective_applies_if(hook, by_id)
        if predicates is not None and (hook_id in on or hook_id in gated):
            rows.append(
                ApplicabilityRow("hook", hook_id, predicates, hook.source_package, hook_id in on)
            )
    return rows


def _artifact_row(
    kind: str, artifact: Rule | Prompt, facts: Mapping[str, Any], repo_root: Path
) -> ApplicabilityRow:
    predicate = dict(artifact.frontmatter.applies_if or {})
    predicates = (predicate,) if predicate else ()
    active = _holds(predicates, facts, repo_root)
    return ApplicabilityRow(
        kind, artifact.frontmatter.id, predicates, artifact.source_package, active
    )


def _holds(predicates: Collection[Mapping[str, Any]], facts: Mapping[str, Any], root: Path) -> bool:
    # sync-time: imports packaging
    from coding_agent_playbook.detector.predicate import evaluate_predicate

    detected = cast("Facts", facts)
    try:
        return all(evaluate_predicate(dict(p), detected, repo_root=root) for p in predicates)
    except ValueError:
        return False


def _plain(value: Any) -> Any:
    """``value`` deep-copied into plain JSON containers: the table never aliases a frontmatter."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class ProtectedRow:
    """One ``protected.entries`` row: a lock entry's path and provenance (no content hash).

    ``sha256`` is kept only for a scoped row (one managed JSON element).

    Example::

        >>> ProtectedRow("AGENTS.md", "composite").to_json()["kind"]
        'composite'
    """

    path: str
    kind: str
    artifact_id: str = ""
    source: str = ""
    scope: str = ""
    sha256: str = ""

    def to_json(self) -> dict[str, str]:
        """The row as rendered: ``sha256`` only when ``scope`` is set."""
        row = {
            "path": self.path,
            "kind": self.kind,
            "artifact_id": self.artifact_id,
            "source": self.source,
            "scope": self.scope,
        }
        if self.scope:
            row["sha256"] = self.sha256
        return row


@dataclass(frozen=True)
class ProtectInputs:
    """What the ``protected`` table is rendered from; all of it machine-independent.

    Example::

        ProtectInputs(entries=protected_rows(prov, managed, root),
                      output_dirs=adapter_output_dirs(adapters, root),
                      packages=("coding_agent_playbook",))
    """

    entries: Sequence[ProtectedRow] = ()
    output_dirs: Sequence[str] = ()
    packages: Sequence[str] = ()
