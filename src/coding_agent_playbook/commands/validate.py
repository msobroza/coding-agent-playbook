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
  pass through the ``[links] allowed_domains`` allowlist.
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
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError

from coding_agent_playbook.adapters._skill_writer import (
    agent_skill_issues,
    has_declared_id,
    skill_id_of,
)
from coding_agent_playbook.commands import _sync_preflight
from coding_agent_playbook.config import parse_links_config
from coding_agent_playbook.detector import evaluate_predicate
from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.evals.validator import validate_tasks
from coding_agent_playbook.links import LinksConfig, classify_link, extract_markdown_links
from coding_agent_playbook.orchestrator import SyncContext
from coding_agent_playbook.renderer import RULE_CALL_RE
from coding_agent_playbook.sources.filesystem import (
    FileSystemArtifactSource,
    _iter_md_files,
    _resource_subdir,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.sources.base import ArtifactSource
    from coding_agent_playbook.types import Prompt, Rule, Skill


@dataclass(frozen=True)
class ValidationError:
    path: str
    message: str


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
        for match in RULE_CALL_RE.finditer(prompt.template_body):
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
        if RULE_CALL_RE.search(rule.template_body):
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


# Artifact kinds whose markdown bodies (and, for skills, references/) are
# link-checked. Eval-task setup/ trees are task *inputs*, not rendered
# artifacts, so they stay out of scope (specs/prL-markdown-links.md).
_LINK_CHECKED_SUBDIRS = ("rules", "prompts", "skills")

_CONFIG_FILENAME = ".coding-agent-playbook.toml"


def _load_links_config(repo_root: Path) -> tuple[LinksConfig, list[ValidationError]]:
    """Parse the ``[links]`` table of ``.coding-agent-playbook.toml``.

    A malformed table degrades to the strict default plus one
    :class:`ValidationError` — the rest of validation still runs.
    """
    config_path = repo_root / _CONFIG_FILENAME
    if not config_path.is_file():
        return LinksConfig(), []
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
        return parse_links_config(data.get("links", {})), []
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        return LinksConfig(), [ValidationError(path=str(config_path), message=f"[links]: {exc}")]


def _scan_markdown_text(
    text: str,
    *,
    path: str,
    base_dir: Path | None,
    root_dir: Path | None,
    links_config: LinksConfig,
) -> list[ValidationError]:
    return [
        ValidationError(
            path=path,
            message=f"markdown link {link.target!r} (line {link.line}): {verdict}",
        )
        for link in extract_markdown_links(text)
        if (
            verdict := classify_link(
                link.target,
                base_dir=base_dir,
                root_dir=root_dir,
                allowed_domains=links_config.allowed_domains,
            )
        )
        is not None
    ]


def _scan_markdown_file(
    md: Path, *, root_dir: Path, links_config: LinksConfig
) -> list[ValidationError]:
    return _scan_markdown_text(
        md.read_text(encoding="utf-8"),
        path=str(md),
        base_dir=md.parent,
        root_dir=root_dir,
        links_config=links_config,
    )


def _check_markdown_links(
    artifact_source: ArtifactSource,
    repo_root: Path,
    links_config: LinksConfig,
) -> list[ValidationError]:
    """Every markdown link in every artifact must be self-contained (PR L).

    Filesystem sources are walked per package — the same pattern as
    :func:`_load_eval_tasks_for_validation` — because skill ``references/``
    files are not carried as paths on the canonical :class:`Skill` type. The
    walk covers rules, prompts, and skills across the engine package, overlay
    packages, and repo-local ``playbook/``; the containment root is the
    package's ``resources/`` (respectively ``playbook/``) so links may cross
    artifact kinds within their layer but never leave the shipped bundle.

    Non-filesystem sources have no on-disk layout to resolve relative targets
    against, so only the external-link policy applies to their bodies.
    """
    errors: list[ValidationError] = []
    if not isinstance(artifact_source, FileSystemArtifactSource):
        for rule in artifact_source.list_rules():
            errors.extend(
                _scan_markdown_text(
                    rule.template_body,
                    path=str(rule.source_path or rule.frontmatter.id),
                    base_dir=None,
                    root_dir=None,
                    links_config=links_config,
                )
            )
        for prompt in artifact_source.list_prompts():
            errors.extend(
                _scan_markdown_text(
                    prompt.template_body,
                    path=str(prompt.source_path or prompt.frontmatter.id),
                    base_dir=None,
                    root_dir=None,
                    links_config=links_config,
                )
            )
        for skill in artifact_source.list_skills():
            errors.extend(
                _scan_markdown_text(
                    skill.body,
                    path=str(skill.frontmatter.get("name", "skill")),
                    base_dir=None,
                    root_dir=None,
                    links_config=links_config,
                )
            )
        return errors

    packages = (artifact_source.engine_package, *artifact_source.overlay_packages)
    for package in packages:
        for subdir in _LINK_CHECKED_SUBDIRS:
            root = _resource_subdir(package, subdir)
            if root is None:
                continue
            for md in _iter_md_files(root):
                errors.extend(
                    _scan_markdown_file(md, root_dir=root.parent, links_config=links_config)
                )
    repo_local_root = repo_root / "playbook"
    for subdir in _LINK_CHECKED_SUBDIRS:
        subdir_path = repo_local_root / subdir
        if not subdir_path.is_dir():
            continue
        for md in _iter_md_files(subdir_path):
            errors.extend(
                _scan_markdown_file(md, root_dir=repo_local_root, links_config=links_config)
            )
    return errors


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
    links_config, links_errors = _load_links_config(repo_root)
    errors.extend(links_errors)
    errors.extend(_check_markdown_links(ctx.artifact_source, repo_root, links_config))
    errors.extend(_check_agent_skills(ctx.skills_resolved, ctx.artifact_source.list_skills()))

    if errors:
        for err in errors:
            print(f"FAIL {err.path}: {err.message}")
        print(f"validation failed with {len(errors)} error(s)")
        return 1
    artifact_count = len(ctx.rules_resolved) + len(ctx.prompts_resolved)
    print(f"OK {artifact_count} artifacts validated")
    return 0
