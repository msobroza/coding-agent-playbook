"""`playbook validate` — cross-reference checks (SPEC §12.6).

Validates:

- ``applies_if`` predicates use only known fact keys (delegates to
  :func:`coding_agent_playbook.detector.evaluate_predicate` and treats a
  ``ValueError`` raised for an unknown key as an error).
- Prompts that call ``{{ rule("X") }}`` declare ``X`` in ``includes_rules:``.
- Rule templates never call ``{{ rule(...) }}`` (rules cannot include rules,
  SPEC invariants).
- Eval-task back-references resolve both directions, via the canonical
  :func:`coding_agent_playbook.evals.validator.validate_tasks` helper.
- Each Jinja-templated artifact compiles cleanly.
- Every markdown link in every artifact is self-contained (PR L): relative
  targets resolve inside the artifact's source layer, external links only
  pass through the ``[links] allowed_domains`` allowlist (``_validate_links``).
- Every package in ``overlays_enabled`` is usable here: it imports without error
  and ships a ``resources/`` directory — the same check ``playbook sync`` refuses
  to run without (``_sync_preflight.unusable_overlays``), so a misspelled pack
  fails here too instead of validating the engine layer alone.
- Every skill is a valid Agent Skill (SPEC §6.3): it declares an ``id`` string
  (id-less skills all collapse into one skill named ``skill``), its id — emitted
  as the ``SKILL.md`` ``name`` and the output directory — matches
  ``^[a-z0-9]+(-[a-z0-9]+)*$`` (1-64 chars), and it has a 1-1024 char
  ``description``. OpenCode silently drops a skill that fails these, so authors
  learn here instead.

All errors aggregate before a single non-zero exit; success prints one line.
Skill files no sync will ever copy — a secret path, or a link leaving the
skill's source dir (SPEC §10.8, §17.3) — are reported as ``warning:`` lines on
stderr and never fail validation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import StrictUndefined, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

from coding_agent_playbook.adapters._skill_sources import refused_skill_files
from coding_agent_playbook.adapters._skill_writer import (
    agent_skill_issues,
    has_declared_id,
    skill_id_of,
)
from coding_agent_playbook.commands import _sync_preflight
from coding_agent_playbook.commands._validate_links import check_markdown_links, load_links_config
from coding_agent_playbook.commands._validation import ValidationError
from coding_agent_playbook.detector import evaluate_predicate
from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.evals.validator import validate_tasks
from coding_agent_playbook.orchestrator import SyncContext
from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.types import Prompt, Rule, Skill


_RULE_CALL_RE = re.compile(r"\{\{\s*rule\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}")


def _check_overlays_usable(overlays: Sequence[str]) -> list[ValidationError]:
    """One error per ``overlays_enabled`` entry that ``playbook sync`` would refuse.

    Without it an unimportable overlay was skipped silently (its artifacts are
    simply absent), so ``validate`` passed a config every sync mode rejects.
    """
    return [
        ValidationError(path="overlays_enabled", message=str(problem))
        for problem in _sync_preflight.unusable_overlays(overlays)
    ]


def _check_applies_if(
    rules: list[Rule], prompts: list[Prompt], facts: Facts, repo_root: Path
) -> list[ValidationError]:
    """Pass each artifact's ``applies_if`` to :func:`evaluate_predicate`; if
    it raises ``ValueError`` (unknown key) record the error.
    """
    errors: list[ValidationError] = []
    for rule in rules:
        predicate = rule.frontmatter.applies_if or {}
        if not predicate:
            continue
        try:
            evaluate_predicate(predicate, facts, repo_root=repo_root)
        except ValueError as exc:
            errors.append(
                ValidationError(
                    path=str(rule.source_path or rule.frontmatter.id),
                    message=f"applies_if: {exc}",
                )
            )
    for prompt in prompts:
        predicate = prompt.frontmatter.applies_if or {}
        if not predicate:
            continue
        try:
            evaluate_predicate(predicate, facts, repo_root=repo_root)
        except ValueError as exc:
            errors.append(
                ValidationError(
                    path=str(prompt.source_path or prompt.frontmatter.id),
                    message=f"applies_if: {exc}",
                )
            )
    return errors


def _check_prompt_rule_calls(prompts: list[Prompt]) -> list[ValidationError]:
    """Prompts that call ``{{ rule("X") }}`` must list ``X`` in
    ``includes_rules:``.
    """
    errors: list[ValidationError] = []
    for prompt in prompts:
        declared = set(prompt.frontmatter.includes_rules or [])
        for match in _RULE_CALL_RE.finditer(prompt.template_body):
            rule_id = match.group(1)
            if rule_id not in declared:
                errors.append(
                    ValidationError(
                        path=str(prompt.source_path or prompt.frontmatter.id),
                        message=(
                            f'body calls {{ rule("{rule_id}") }} but {rule_id!r} '
                            "is not in includes_rules"
                        ),
                    )
                )
    return errors


def _check_rule_bodies_do_not_include_rules(rules: list[Rule]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for rule in rules:
        if _RULE_CALL_RE.search(rule.template_body):
            errors.append(
                ValidationError(
                    path=str(rule.source_path or rule.frontmatter.id),
                    message="body calls `{{ rule(...) }}` — rules cannot include other rules",
                )
            )
    return errors


def _check_jinja_compiles(rules: list[Rule], prompts: list[Prompt]) -> list[ValidationError]:
    # Syntax-only parse — no rule_registry/no facts needed. Sandboxed like the
    # renderer's environment so no Jinja construction site is unsandboxed (prK §P1).
    env = SandboxedEnvironment(autoescape=False, undefined=StrictUndefined)
    errors: list[ValidationError] = []
    for rule in rules:
        if not rule.is_templated:
            continue
        try:
            env.parse(rule.template_body)
        except TemplateSyntaxError as exc:
            errors.append(
                ValidationError(
                    path=str(rule.source_path or rule.frontmatter.id),
                    message=f"Jinja syntax error: {exc.message}",
                )
            )
    for prompt in prompts:
        if not prompt.is_templated:
            continue
        try:
            env.parse(prompt.template_body)
        except TemplateSyntaxError as exc:
            errors.append(
                ValidationError(
                    path=str(prompt.source_path or prompt.frontmatter.id),
                    message=f"Jinja syntax error: {exc.message}",
                )
            )
    return errors


def _load_eval_tasks_for_validation(
    ctx: SyncContext,
) -> tuple[list[EvalTask], list[ValidationError]]:
    """Walk every eval-task directory and load each ``task.toml`` independently,
    aggregating per-task loader errors instead of fail-fasting.

    Mirrors :meth:`FileSystemArtifactSource.list_eval_tasks` but catches the
    per-task :exc:`FileNotFoundError` / :exc:`ValueError` raised by the loader
    and converts them to :class:`ValidationError` entries. Malformed TOML or
    schema violations don't abort the rest of validation — the caller still
    runs ``validate_tasks`` against the tasks that did load.

    Non-filesystem :class:`ArtifactSource` implementations have no per-package
    layout to walk, so we fall back to :meth:`ArtifactSource.list_eval_tasks`
    and accept that those sources cannot surface per-file loader errors here —
    that's their responsibility, not ours.
    """
    artifact_source = ctx.artifact_source
    if not isinstance(artifact_source, FileSystemArtifactSource):
        return list(artifact_source.list_eval_tasks()), []
    loaded = [
        _load_eval_task(task_dir, label)
        for label, root in artifact_source.layer_roots("eval_tasks")
        for task_dir in discover_eval_task_dirs(root)
    ]
    tasks = [item for item in loaded if not isinstance(item, ValidationError)]
    return tasks, [item for item in loaded if isinstance(item, ValidationError)]


def _load_eval_task(task_dir: Path, source_package: str) -> EvalTask | ValidationError:
    """Load one ``task.toml``, or return its loader failure as a finding."""
    try:
        return load_eval_task_from_dir(task_dir, source_package=source_package)
    except (FileNotFoundError, ValueError) as exc:
        return ValidationError(path=str(task_dir / "task.toml"), message=str(exc))


def _check_eval_tasks(ctx: SyncContext) -> list[ValidationError]:
    """Run the canonical eval-task validator (SPEC §15.2 + §6.5.5).

    Combines per-task loader failures (malformed TOML / missing required
    fields) with the cross-reference rules from
    :func:`coding_agent_playbook.evals.validator.validate_tasks`.
    """
    tasks, load_errors = _load_eval_tasks_for_validation(ctx)
    cross_errors = validate_tasks(tasks, ctx.prompts_resolved)
    return [
        *load_errors,
        *[ValidationError(path=str(e.path), message=e.message) for e in cross_errors],
    ]


def _check_agent_skills(resolved: list[Skill], loaded: list[Skill]) -> list[ValidationError]:
    """Flag skills that break the Agent Skills ``id``/``name``/``description`` rules.

    Checks the emitted (``resolved``) skills that declare an id, plus every
    id-less skill from the pre-merge ``loaded`` list: id-less skills all merge
    under ``"skill"``, so the merge silently drops all but one of them and only
    ``loaded`` still holds each one (and each is reported exactly once).
    """
    with_id = [skill for skill in resolved if has_declared_id(skill)]
    without_id = [skill for skill in loaded if not has_declared_id(skill)]
    return [
        ValidationError(path=_skill_label(skill), message=issue)
        for skill in [*with_id, *without_id]
        for issue in agent_skill_issues(skill)
    ]


def _skill_label(skill: Skill) -> str:
    """Locate ``skill`` for an error line (a canonical :class:`Skill` has no source path).

    Example: ``skills/query-db (<repo-local>)``; an id-less skill is named by its
    authored ``name`` and, when it has one, its ``scripts/``/``references/`` parent dir.
    """
    if has_declared_id(skill):
        return f"skills/{skill_id_of(skill)} ({skill.source_package})"
    source_dir = skill.scripts_dir or skill.references_dir
    where = f", at {source_dir.parent}" if source_dir is not None else ""
    name = skill.frontmatter.get("name", "?")
    return f"skills/<no id; name {name!r}{where}> ({skill.source_package})"


def _warn_refused_skill_files(skills: list[Skill]) -> list[str]:
    """Warn on stderr about skill files ``playbook sync`` never copies; return the lines.

    Example::

        _warn_refused_skill_files(ctx.skills_resolved)  # [] for a clean skill set
    """
    lines = [
        f"warning: {_skill_label(skill)}: {item.path} is never copied: {item.reason}"
        for skill in skills
        for item in refused_skill_files(skill)
    ]
    for line in lines:
        print(line, file=sys.stderr)
    return lines


def run(args: argparse.Namespace) -> int:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    ctx = SyncContext.from_repo(repo_root)
    errors: list[ValidationError] = []
    errors.extend(_check_overlays_usable(ctx.config.overlays_enabled))
    errors.extend(_check_applies_if(ctx.rules_resolved, ctx.prompts_resolved, ctx.facts, repo_root))
    errors.extend(_check_prompt_rule_calls(ctx.prompts_resolved))
    errors.extend(_check_rule_bodies_do_not_include_rules(ctx.rules_resolved))
    errors.extend(_check_jinja_compiles(ctx.rules_resolved, ctx.prompts_resolved))
    errors.extend(_check_eval_tasks(ctx))
    links_config, links_errors = load_links_config(repo_root)
    errors.extend(links_errors)
    errors.extend(check_markdown_links(ctx.artifact_source, repo_root, links_config))
    errors.extend(_check_agent_skills(ctx.skills_resolved, ctx.artifact_source.list_skills()))
    _warn_refused_skill_files(ctx.skills_resolved)

    if errors:
        for err in errors:
            print(f"FAIL {err.path}: {err.message}")
        print(f"validation failed with {len(errors)} error(s)")
        return 1
    artifact_count = len(ctx.rules_resolved) + len(ctx.prompts_resolved)
    print(f"OK {artifact_count} artifacts validated")
    return 0
