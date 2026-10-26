"""The graded set: the prompts eval samples grade, plus the rules those prompts include.

:func:`graded_set` is the only definition (CONTEXT.md: Graded set). It takes the
graded prompt ids as an argument, so the caller decides where they come from:
today :func:`core_graded_prompt_ids` reads each core sample's ``prompt_id``, which
the sample's task directory sets (#302); passing the task registry's prompt ids
(``evals.task_registry``) instead changes nothing here.

Only the engine's own layer is graded: editions exist for core only (ADR 0012).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.catalog.source import FileSystemArtifactSource

__all__ = ["GradedSet", "GradedSetError", "core_graded_prompt_ids", "graded_set"]


class GradedSetError(ValueError):
    """A graded prompt id or an included rule id that resolves to no core artifact."""


@dataclass(frozen=True)
class GradedSet:
    """The graded prompts and the rules they include, each sorted by id.

    Example::

        >>> GradedSet((), ()).prompts
        ()
    """

    prompts: tuple[Prompt, ...]
    rules: tuple[Rule, ...]


def graded_set(
    prompt_ids: Iterable[str], prompts: Sequence[Prompt], rules: Sequence[Rule]
) -> GradedSet:
    """The prompts named by ``prompt_ids`` and every rule they list in ``includes_rules``.

    ``prompts`` and ``rules`` are the engine layer's artifacts. A prompt id or an
    included rule id with no match raises :class:`GradedSetError` naming it and
    the ids that exist.

    Example::

        >>> graded_set(["review"], core_prompts, core_rules).rules  # doctest: +SKIP
        (Rule(...), ...)
    """
    prompts_by_id = {prompt.frontmatter.id: prompt for prompt in prompts}
    rules_by_id = {rule.frontmatter.id: rule for rule in rules}
    graded = [_lookup(prompts_by_id, pid, "prompt") for pid in sorted(set(prompt_ids))]
    rule_ids = sorted({rid for prompt in graded for rid in prompt.frontmatter.includes_rules})
    included = [_lookup(rules_by_id, rid, "rule") for rid in rule_ids]
    return GradedSet(prompts=tuple(graded), rules=tuple(included))


def _lookup[T](by_id: dict[str, T], artifact_id: str, kind: str) -> T:
    found = by_id.get(artifact_id)
    if found is None:
        raise GradedSetError(
            f"graded {kind} {artifact_id!r} is not a core {kind}; core has {sorted(by_id)}"
        )
    return found


def core_graded_prompt_ids(source: FileSystemArtifactSource) -> list[str]:
    """The ``prompt_id`` of every core eval sample in ``source``, sorted and unique.

    Example::

        >>> core_graded_prompt_ids(FileSystemArtifactSource(repo_root=Path(".")))  # doctest: +SKIP
        ['characterize', 'explain', ...]
    """
    samples = source.list_eval_samples()
    return sorted({s.prompt_id for s in samples if s.source_package == ENGINE_PACKAGE})
