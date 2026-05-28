"""`cap validate` — cross-reference checks (SPEC §12.6).

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

All errors aggregate before a single non-zero exit; success prints one line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError

from coding_agent_playbook.detector import evaluate_predicate
from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.evals.validator import validate_tasks
from coding_agent_playbook.orchestrator import SyncContext
from coding_agent_playbook.sources.filesystem import (
    FileSystemArtifactSource,
    _resource_subdir,
)

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.types import Prompt, Rule


@dataclass(frozen=True)
class ValidationError:
    path: str
    message: str


_RULE_CALL_RE = re.compile(r"\{\{\s*rule\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}")


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
    # Syntax-only parse — no rule_registry/no facts needed.
    env = Environment(autoescape=False, undefined=StrictUndefined)
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
    tasks: list[EvalTask] = []
    errors: list[ValidationError] = []
    repo_root = ctx.repo_root
    artifact_source = ctx.artifact_source
    # Reach for the source's package list via its public read-only properties.
    # Non-filesystem sources skip the per-package loader-error aggregation and
    # delegate to ``list_eval_tasks()`` instead, so the validator still sees
    # the task set even when the source isn't filesystem-backed.
    if not isinstance(artifact_source, FileSystemArtifactSource):
        return list(artifact_source.list_eval_tasks()), errors
    engine_package = artifact_source.engine_package
    overlay_packages = list(artifact_source.overlay_packages)
    for package in (engine_package, *overlay_packages):
        root = _resource_subdir(package, "eval_tasks")
        if root is None:
            continue
        for task_dir in discover_eval_task_dirs(root):
            try:
                tasks.append(load_eval_task_from_dir(task_dir, source_package=package))
            except (FileNotFoundError, ValueError) as exc:
                errors.append(
                    ValidationError(
                        path=str(task_dir / "task.toml"),
                        message=str(exc),
                    )
                )
    repo_local = repo_root / "playbook" / "eval_tasks"
    for task_dir in discover_eval_task_dirs(repo_local):
        try:
            tasks.append(load_eval_task_from_dir(task_dir, source_package="<repo-local>"))
        except (FileNotFoundError, ValueError) as exc:
            errors.append(
                ValidationError(
                    path=str(task_dir / "task.toml"),
                    message=str(exc),
                )
            )
    return tasks, errors


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


def run(args: argparse.Namespace) -> int:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    ctx = SyncContext.from_repo(repo_root)
    errors: list[ValidationError] = []
    errors.extend(_check_applies_if(ctx.rules_resolved, ctx.prompts_resolved, ctx.facts, repo_root))
    errors.extend(_check_prompt_rule_calls(ctx.prompts_resolved))
    errors.extend(_check_rule_bodies_do_not_include_rules(ctx.rules_resolved))
    errors.extend(_check_jinja_compiles(ctx.rules_resolved, ctx.prompts_resolved))
    errors.extend(_check_eval_tasks(ctx))

    if errors:
        for err in errors:
            print(f"FAIL {err.path}: {err.message}")
        print(f"validation failed with {len(errors)} error(s)")
        return 1
    artifact_count = len(ctx.rules_resolved) + len(ctx.prompts_resolved)
    print(f"OK {artifact_count} artifacts validated")
    return 0
