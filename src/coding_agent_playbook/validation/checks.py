"""The validation rule set — cross-reference checks over canonical artifacts (SPEC §12.6).

Behind ``playbook validate`` (the command and its printer stay in
:mod:`coding_agent_playbook.commands.validate`) and the ``playbook sync`` gate.
Validates:

- ``applies_if`` predicates use only known fact keys and well-formed values
  (delegates to :func:`coding_agent_playbook.detector.predicate.evaluate_predicate` one key
  at a time, as hooks do, and treats each ``ValueError`` as an error).
- Prompts never call ``{{ rule() }}``; every ``includes_rules`` id names a rule
  (``validation.prompts``, specs/prS-skills-context.md §7.5).
- Every prompt ``output_contract`` entry compiles as a Python regex (fail-closed,
  like ``AnswerMatchesCheck``; specs/prK-hook-pack.md §E.2).
- Rule templates never call ``{{ rule(...) }}`` (rules cannot include rules,
  SPEC invariants).
- Eval-sample back-references resolve both directions, via the canonical
  :func:`coding_agent_playbook.evals.validator.validate_samples` helper.
- Each Jinja-templated artifact compiles cleanly.
- Every markdown link in every artifact is self-contained (PR L): relative
  targets resolve inside the artifact's source layer, external links only
  pass through the ``[links] allowed_domains`` allowlist (``validation._links``).
- Every ``overlays_enabled`` entry is usable here: an overlay package imports
  without error and ships a ``resources/`` directory, and a bundled-plugin name
  matches a ``catalog/plugins/<leaf>/`` directory — the same check ``playbook
  sync`` refuses to run without (``validation.preflight.unusable_overlays``), so a
  misspelled bundled plugin fails here too instead of validating the engine
  layer alone.
- The ``framework`` key names a framework, at most one framework is enabled,
  and its ``framework.toml`` and capability tags are sound (D57, D77;
  ``validation._framework``).
- Every skill is a valid Agent Skill (SPEC §6.3): it declares an ``id`` string
  (id-less skills all collapse into one skill named ``skill``), its id — emitted
  as the ``SKILL.md`` ``name`` and the output directory — matches
  ``^[a-z0-9]+(-[a-z0-9]+)*$`` (1-64 chars), and it has a 1-1024 char
  ``description``. OpenCode silently drops a skill that fails these, so authors
  learn here instead.
- Member rules and ``playbook:`` blocks (prS §6.6 V3-V14, W1-W3,
  ``validation._skills``): a rule's ``skill`` names a merged skill that takes
  members, and that skill's block, description fit and references are sound.
- Every hook honours the trust contract H1-H21 (specs/prK-lifecycle-hooks.md
  §B.5, ``validation._hooks``): a malformed ``HOOK.md`` is a ``FAIL`` line, not a
  traceback (P8c); degraded cells and clamped timeouts are ``warning:`` lines.

All findings aggregate into one :class:`ValidationFindings`;
:func:`collect_validation_findings` is the rule set and prints nothing.
``commands.validate.run`` exits non-zero once on any error, and on success
prints one line, counting rules, prompts and hooks; ``playbook sync`` runs it first (:func:`sync_gate_errors`) and
refuses to write on any error (prK §P P8b). Without a consumer
config, validate checks the engine, the checkout's ``src/*/resources/`` and
``playbook/``, skipping the consumer-config checks (``validation.context``).
Skill files no sync will ever copy — a secret path, or a link leaving the
skill's source dir (SPEC §10.8, §17.3) — are reported as ``warning:`` lines on
stderr and never fail validation.
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.config.tables.links import LinksConfig
from coding_agent_playbook.detector.predicate import evaluate_predicate
from coding_agent_playbook.evals.loader import (
    discover_eval_sample_dirs,
    load_eval_sample_from_dir,
)
from coding_agent_playbook.evals.validator import validate_samples
from coding_agent_playbook.generated_output.source_files import refused_skill_files
from coding_agent_playbook.rendering.jinja import RULE_CALL_RE, jinja_syntax_error
from coding_agent_playbook.skills.naming import agent_skill_issues, has_declared_id
from coding_agent_playbook.validation import preflight as _sync_preflight
from coding_agent_playbook.validation._framework import check_framework
from coding_agent_playbook.validation._frontmatter import (
    check_lint_codes,
    check_rule_shape,
    check_write_scope,
)
from coding_agent_playbook.validation._hooks import check_hooks
from coding_agent_playbook.validation._links import check_markdown_links, load_links_config
from coding_agent_playbook.validation._skills import (
    check_rule_skills,
    check_skill_membership,
)
from coding_agent_playbook.validation.findings import (
    ValidationError,
    ValidationFindings,
    report_validation_warnings,
    skill_label,
)
from coding_agent_playbook.validation.prompts import check_prompt_rule_references

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.validation.context import SyncContext


def _check_overlays_usable(overlays: Sequence[str]) -> list[ValidationError]:
    """One error per ``overlays_enabled`` entry that ``playbook sync`` would refuse.

    Without it an unimportable overlay was skipped silently (its artifacts are
    simply absent), so ``validate`` passed a config every sync mode rejects.
    """
    return [
        ValidationError(path="overlays_enabled", message=str(problem))
        for problem in _sync_preflight.unusable_overlays(overlays)
    ]


def _consumer_config_errors(ctx: SyncContext) -> list[ValidationError]:
    """The checks that need a consumer config: usable overlays, then the framework (D57)."""
    errors = _check_overlays_usable(ctx.config.overlays_enabled)
    errors.extend(check_framework(ctx.config, ctx.artifact_source.list_skills()))
    return errors


def _applies_if_errors(
    path: str, predicate: Mapping[str, Any], facts: Facts, repo_root: Path
) -> list[ValidationError]:
    """One error per ``applies_if`` key that ``evaluate_predicate`` rejects, each key alone.

    ``evaluate_predicate`` returns at the first key that does not hold, so a
    malformed key after it would pass unseen; hook predicates are already
    checked key by key (hooks/contract/contract.py).

    Example: ``_applies_if_errors("r.md", {"package_manager": "pipenv"}, {}, root)``
    returns one error naming ``'pipenv'`` and the four allowed managers.
    """
    errors: list[ValidationError] = []
    for key, value in predicate.items():
        try:
            evaluate_predicate({key: value}, facts, repo_root=repo_root)
        except ValueError as exc:
            errors.append(ValidationError(path=path, message=f"applies_if: {exc}"))
    return errors


def _check_applies_if(
    rules: list[Rule], prompts: list[Prompt], facts: Facts, repo_root: Path
) -> list[ValidationError]:
    """Validate every rule's and prompt's ``applies_if``, key by key."""
    artifacts: list[Rule | Prompt] = [*rules, *prompts]
    return [
        error
        for artifact in artifacts
        for error in _applies_if_errors(
            str(artifact.source_path or artifact.frontmatter.id),
            artifact.frontmatter.applies_if or {},
            facts,
            repo_root,
        )
    ]


_CONTRACT_SHAPE = (
    "expected a list of Python regular expressions, e.g. "
    "['(?im)^\\W*(approve|request changes)\\W*$']"
)


def _check_output_contracts(prompts: list[Prompt]) -> list[ValidationError]:
    """One error per ``output_contract`` entry that is not a compilable regex.

    Fail-closed like ``AnswerMatchesCheck``: a malformed pattern is an authoring
    error caught here, never a Stop stage that silently matches nothing.
    """
    errors: list[ValidationError] = []
    for prompt in prompts:
        contract: object = prompt.frontmatter.output_contract
        where = str(prompt.source_path or prompt.frontmatter.id)
        if not isinstance(contract, list):
            errors.append(
                ValidationError(
                    path=where, message=f"output_contract {contract!r}: {_CONTRACT_SHAPE}"
                )
            )
            continue
        errors.extend(
            ValidationError(path=where, message=f"output_contract pattern {pattern!r}: {problem}")
            for pattern in contract
            if (problem := _regex_problem(pattern)) is not None
        )
    return errors


def _regex_problem(pattern: object) -> str | None:
    """Why ``pattern`` is no usable contract regex, else ``None``."""
    if not isinstance(pattern, str) or not pattern:
        return _CONTRACT_SHAPE
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"is not a valid Python regular expression ({exc}); {_CONTRACT_SHAPE}"
    return None


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
    """One error per templated rule or prompt whose body does not parse."""
    artifacts: list[Rule | Prompt] = [*rules, *prompts]
    return [
        ValidationError(
            path=str(artifact.source_path or artifact.frontmatter.id),
            message=f"Jinja syntax error: {problem}",
        )
        for artifact in artifacts
        if artifact.is_templated
        and (problem := jinja_syntax_error(artifact.template_body)) is not None
    ]


def _load_eval_samples_for_validation(
    ctx: SyncContext,
) -> tuple[list[EvalSample], list[ValidationError]]:
    """Walk every eval-sample directory and load each ``sample.toml`` independently,
    aggregating per-sample loader errors instead of fail-fasting.

    Mirrors :meth:`FileSystemArtifactSource.list_eval_samples` but catches the
    per-sample :exc:`FileNotFoundError` / :exc:`ValueError` raised by the loader
    and converts them to :class:`ValidationError` entries. Malformed TOML or
    schema violations don't abort the rest of validation — the caller still
    runs ``validate_samples`` against the samples that did load.

    Non-filesystem :class:`ArtifactSource` implementations have no per-package
    layout to walk, so we fall back to :meth:`ArtifactSource.list_eval_samples`
    and accept that those sources cannot surface per-file loader errors here —
    that's their responsibility, not ours.
    """
    artifact_source = ctx.artifact_source
    if not isinstance(artifact_source, FileSystemArtifactSource):
        return list(artifact_source.list_eval_samples()), []
    loaded = [
        _load_eval_sample(sample_dir, label)
        for label, root in artifact_source.layer_roots("eval_samples")
        for sample_dir in discover_eval_sample_dirs(root)
    ]
    samples = [item for item in loaded if not isinstance(item, ValidationError)]
    return samples, [item for item in loaded if isinstance(item, ValidationError)]


def _load_eval_sample(sample_dir: Path, source_package: str) -> EvalSample | ValidationError:
    """Load one ``sample.toml``, or return its loader failure as a finding."""
    try:
        return load_eval_sample_from_dir(sample_dir, source_package=source_package)
    except (FileNotFoundError, ValueError) as exc:
        return ValidationError(path=str(sample_dir / "sample.toml"), message=str(exc))


def _check_eval_samples(ctx: SyncContext) -> list[ValidationError]:
    """Run the canonical eval-sample validator (SPEC §15.2 + §6.5.5).

    Combines per-sample loader failures (malformed TOML / missing required
    fields) with the cross-reference rules from
    :func:`coding_agent_playbook.evals.validator.validate_samples`.
    """
    samples, load_errors = _load_eval_samples_for_validation(ctx)
    cross_errors = validate_samples(samples, ctx.prompts_resolved)
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
        ValidationError(path=skill_label(skill), message=issue)
        for skill in [*with_id, *without_id]
        for issue in agent_skill_issues(skill)
    ]


def warn_refused_skill_files(skills: list[Skill]) -> list[str]:
    """Warn on stderr about skill files ``playbook sync`` never copies; return the lines.

    Example::

        warn_refused_skill_files(ctx.skills_resolved)  # [] for a clean skill set
    """
    lines = [
        f"warning: {skill_label(skill)}: {item.path} is never copied: {item.reason}"
        for skill in skills
        for item in refused_skill_files(skill)
    ]
    for line in lines:
        print(line, file=sys.stderr)
    return lines


def collect_validation_findings(
    ctx: SyncContext, *, config_less: bool = False, local_policy_is_error: bool = True
) -> ValidationFindings:
    """Run every validate rule against ``ctx``; every error and warning, in check order.

    The single rule set behind ``playbook validate`` and the gate in front of
    ``playbook sync`` (prK §P P8b). ``config_less`` skips the checks that read
    the consumer config (:data:`coding_agent_playbook.validation.context.CONSUMER_CONFIG_CHECKS`):
    overlay usability, and the ``[links]`` allowlist — external links then
    meet the strict default. ``local_policy_is_error=False`` (the sync gate)
    downgrades a ``[hooks]`` / ``[guardrails]`` table in ``.local.toml`` to a
    warning (H21, §B.1). Prints nothing; never raises for a finding.

    Example::

        >>> collect_validation_findings(SyncContext.from_repo(Path("."))).errors  # doctest: +SKIP
        []
    """
    errors = _artifact_errors(ctx, config_less=config_less)
    skills = check_rule_skills(ctx.rules_resolved, ctx.skills_resolved)
    hook_errors, hook_warnings = check_hooks(ctx, local_policy_is_error=local_policy_is_error)
    return ValidationFindings(
        [*errors, *skills.errors, *hook_errors], [*skills.warnings, *hook_warnings]
    )


def collect_validation_errors(
    ctx: SyncContext, *, config_less: bool = False
) -> list[ValidationError]:
    """The errors of :func:`collect_validation_findings` (validate's own severities).

    Example::

        >>> collect_validation_errors(SyncContext.from_repo(Path(".")))  # doctest: +SKIP
        []
    """
    return collect_validation_findings(ctx, config_less=config_less).errors


def sync_gate_errors(ctx: SyncContext) -> list[ValidationError]:
    """The validate gate of ``playbook sync``: validate's errors, its warnings on stderr.

    Unlike ``playbook validate``, a ``.local.toml`` ``[hooks]`` / ``[guardrails]``
    table only warns here: it is ignored, and a developer's own local file must
    not block their sync (§B.1).

    Example::

        >>> sync_gate_errors(SyncContext.from_repo(Path(".")))  # doctest: +SKIP
        []
    """
    findings = collect_validation_findings(ctx, local_policy_is_error=False)
    report_validation_warnings(findings.warnings, sys.stderr)
    return findings.errors


def _artifact_errors(ctx: SyncContext, *, config_less: bool) -> list[ValidationError]:
    """The rule, prompt, eval-sample, link and skill checks (everything but hooks)."""
    rules, prompts = ctx.rules_resolved, ctx.prompts_resolved
    errors = [] if config_less else _consumer_config_errors(ctx)
    errors.extend(
        ValidationError(path=str(e.path), message=e.problem) for e in ctx.rule_load_errors
    )
    errors.extend(check_rule_shape(rules))
    errors.extend(_check_applies_if(rules, prompts, ctx.facts, ctx.repo_root))
    errors.extend(check_prompt_rule_references(prompts, {r.frontmatter.id for r in rules}))
    errors.extend(_check_output_contracts(prompts))
    errors.extend(check_write_scope(prompts))
    errors.extend(
        check_lint_codes(
            rules,
            lambda predicate: evaluate_predicate(predicate, ctx.facts, repo_root=ctx.repo_root),
        )
    )
    errors.extend(_check_rule_bodies_do_not_include_rules(rules))
    errors.extend(_check_jinja_compiles(rules, prompts))
    errors.extend(_check_eval_samples(ctx))
    links_config, links_errors = (
        (LinksConfig(), []) if config_less else load_links_config(ctx.repo_root)
    )
    errors.extend(links_errors)
    errors.extend(check_markdown_links(ctx.artifact_source, ctx.repo_root, links_config))
    errors.extend(_check_agent_skills(ctx.skills_resolved, ctx.artifact_source.list_skills()))
    errors.extend(
        check_skill_membership(rules, ctx.skills_resolved, all_rules=ctx.rule_definitions)
    )
    return errors
