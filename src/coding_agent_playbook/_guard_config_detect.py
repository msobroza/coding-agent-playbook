"""The ``facts`` and ``applicability`` tables of ``guard_config.json`` (specs/prK-hook-pack.md §E.0.5, §E.1).

resync-on-detector-input-change decides from data rendered here, so its cheap
path is one ``tomllib`` read and a set comparison:

- ``facts``: the detector's dependency names (runtime and dev groups) and the
  presence flags (``has_dockerfile``, ``has_ci``, ``has_notebooks``), the
  subset of ``detect()`` a mid-session edit can change, plus the detected
  ``package_manager`` (dependency-allowlist-guard, §E.4);
- ``applicability``: ``{kind, id, applies_if, source, active}`` for every
  merged rule and prompt and every hook that only applicability keeps off.
  ``applies_if`` is a list of predicates that must all hold (a hook's own,
  then its linked rule's; ``[]`` = always) and ``active`` whether they held at
  this sync, so the runtime can name what a fact change turns on or off
  without rebuilding a ``SyncContext`` (``orchestrator`` imports jinja2).

Both depend only on the repository (``detect()`` and ``has_file`` read the
repo, never the machine), so ``sync --check`` byte-compares them. Split out of
``guard_config`` for the module-size budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Protocol, cast

from coding_agent_playbook.hook_policy import APPLICABILITY_GATES, effective_applies_if

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.hook_policy import ResolvedHook, SkippedHook
    from coding_agent_playbook.types import Hook, Prompt, Rule

__all__ = [
    "ApplicabilityRow",
    "DetectInputs",
    "HookView",
    "applicability_rows",
    "applicability_table",
    "facts_table",
]

_FLAGS: Final = ("has_ci", "has_dockerfile", "has_notebooks")


class HookView(Protocol):
    """An effective hook view: ``hook_policy.EffectiveHooks`` or the sync's ``SyncHooks``."""

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


def facts_table(facts: Mapping[str, Any]) -> dict[str, Any]:
    """The ``facts`` table: sorted dependency names, the presence flags, the package manager.

    Example::

        >>> facts_table({"dependencies": {"torch": ">=2"}})["dependencies"]
        ['torch']
    """
    table: dict[str, Any] = {
        "dependencies": sorted(facts.get("dependencies", {})),
        "dev_dependencies": sorted(facts.get("dev_dependencies", {})),
    }
    table.update({flag: bool(facts.get(flag, False)) for flag in _FLAGS})
    manager = facts.get("package_manager")
    if isinstance(manager, str):  # dependency-allowlist-guard's tier (a), §E.4
        table["package_manager"] = manager
    return table


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


def applicability_table(rows: Iterable[ApplicabilityRow]) -> list[dict[str, Any]]:
    """The rendered ``applicability`` list, sorted by ``(kind, id)``.

    Example::

        >>> applicability_table([])
        []
    """
    return [row.to_json() for row in sorted(rows, key=lambda row: (row.kind, row.id))]


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
    from coding_agent_playbook.detector import evaluate_predicate  # sync-time: imports packaging

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
