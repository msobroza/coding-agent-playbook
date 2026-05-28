"""`cap validate` — cross-reference checks (SPEC §12.6).

Validates:

- ``applies_if`` predicates use only known fact keys (delegates to
  :func:`coding_agent_playbook.detector.evaluate_predicate` and treats a
  ``ValueError`` raised for an unknown key as an error).
- Prompts that call ``{{ rule("X") }}`` declare ``X`` in ``includes_rules:``.
- Rule templates never call ``{{ rule(...) }}`` (rules cannot include rules,
  SPEC invariants).
- Eval-task back-references resolve both directions:
    * each prompt's ``eval_tasks:`` IDs match an on-disk
      ``eval_tasks/<id>/task.toml`` (PR 11 will refactor to use the canonical
      :class:`EvalTask`).
    * each ``task.toml``'s ``prompt_id`` matches a real prompt.
- Each Jinja-templated artifact compiles cleanly.

All errors aggregate before a single non-zero exit; success prints one line.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError

from coding_agent_playbook.detector import evaluate_predicate
from coding_agent_playbook.orchestrator import SyncContext

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.detector import Facts
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


def _discover_eval_tasks(repo_root: Path) -> dict[str, Path]:
    """Walk ``<repo>/playbook/eval_tasks/<id>/task.toml`` (PR 11 will widen
    this to also walk engine + overlay packages). Returns a mapping of
    task-id → toml-path.
    """
    tasks: dict[str, Path] = {}
    base = repo_root / "playbook" / "eval_tasks"
    if base.is_dir():
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            task_toml = entry / "task.toml"
            if task_toml.is_file():
                tasks[entry.name] = task_toml
    return tasks


def _check_eval_tasks(prompts: list[Prompt], tasks: dict[str, Path]) -> list[ValidationError]:
    """Two-way check: every prompt-declared task exists on disk, and every
    on-disk task references an existing prompt.
    """
    errors: list[ValidationError] = []
    prompt_ids = {p.frontmatter.id for p in prompts}
    prompt_task_decls: dict[str, list[str]] = {}
    for prompt in prompts:
        declared = list(prompt.frontmatter.eval_tasks or [])
        prompt_task_decls[prompt.frontmatter.id] = declared
        for task_id in declared:
            if task_id not in tasks:
                errors.append(
                    ValidationError(
                        path=str(prompt.source_path or prompt.frontmatter.id),
                        message=(
                            f"declares eval_task {task_id!r} but eval_tasks/{task_id}/ not found"
                        ),
                    )
                )
    for _task_id, toml_path in tasks.items():
        try:
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            errors.append(
                ValidationError(
                    path=str(toml_path),
                    message=f"task.toml is malformed: {exc}",
                )
            )
            continue
        prompt_id = data.get("prompt_id")
        if not isinstance(prompt_id, str):
            errors.append(
                ValidationError(
                    path=str(toml_path),
                    message="task.toml missing required string field 'prompt_id'",
                )
            )
            continue
        if prompt_id not in prompt_ids:
            errors.append(
                ValidationError(
                    path=str(toml_path),
                    message=f"prompt_id {prompt_id!r} does not exist",
                )
            )
    return errors


def run(args: argparse.Namespace) -> int:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    ctx = SyncContext.from_repo(repo_root)
    errors: list[ValidationError] = []
    errors.extend(_check_applies_if(ctx.rules_resolved, ctx.prompts_resolved, ctx.facts, repo_root))
    errors.extend(_check_prompt_rule_calls(ctx.prompts_resolved))
    errors.extend(_check_rule_bodies_do_not_include_rules(ctx.rules_resolved))
    errors.extend(_check_jinja_compiles(ctx.rules_resolved, ctx.prompts_resolved))
    tasks = _discover_eval_tasks(repo_root)
    errors.extend(_check_eval_tasks(ctx.prompts_resolved, tasks))

    if errors:
        for err in errors:
            print(f"FAIL {err.path}: {err.message}")
        print(f"validation failed with {len(errors)} error(s)")
        return 1
    artifact_count = len(ctx.rules_resolved) + len(ctx.prompts_resolved)
    print(f"OK {artifact_count} artifacts validated")
    return 0
