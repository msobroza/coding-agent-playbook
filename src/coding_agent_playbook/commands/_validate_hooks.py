"""``playbook validate``'s hook trust contract, H1-H21 (specs/prK-lifecycle-hooks.md §B.5, lock L6).

:func:`check_hooks` gathers every hook finding of a context into
:class:`~coding_agent_playbook.commands._validation.ValidationError` lines:

- H1 (and H2's layout half): each ``HOOK.md`` that did not load, which a
  context built with ``tolerate_hook_errors=True`` records (P8c);
- H2, H14, H15: the layer overrides the merge refused (``hook_violations``);
- per hook, every layer's definition: ``hook_policy.classify_hook`` (with the
  handler registry, so H6 checks each builtin's declaration) and the
  H19 body checks (a Jinja syntax error, a ``rule()`` call); H19's links are
  ``_validate_links``'s, with ``hooks`` among the link-checked kinds;
- across hooks, artifacts and the committed config: the ``[hooks]`` /
  ``[guardrails]`` parse (H21) and ``hook_policy.classify_hook_set``.

Split out of ``commands/validate.py`` for its size budget; it imports only the
leaf ``_validation``, never ``validate``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.commands._validation import (
    RULE_CALL_RE,
    ValidationError,
    jinja_syntax_error,
)
from coding_agent_playbook.hook_policy import (
    HookCheckContext,
    HookIssue,
    HookSetInputs,
    RegistryCatalog,
    classify_hook,
    classify_hook_set,
    resolve_effective_hooks,
)
from coding_agent_playbook.hook_policy._findings import hook_location
from coding_agent_playbook.hooks_config import GuardrailsConfig
from coding_agent_playbook.orchestrator import engine_package_of
from coding_agent_playbook.sources.filesystem import FileSystemStateSource

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from coding_agent_playbook.hook_policy import HandlerCatalog
    from coding_agent_playbook.hooks_config import HooksConfig
    from coding_agent_playbook.orchestrator import SyncContext
    from coding_agent_playbook.types import Hook, HookSchemaError


def check_hooks(
    ctx: SyncContext, *, local_policy_is_error: bool = True
) -> tuple[list[ValidationError], list[ValidationError]]:
    """``(errors, warnings)`` of every hook rule H1-H21 against ``ctx``; prints nothing.

    ``local_policy_is_error=False`` (the sync gate) reports a ``[hooks]`` /
    ``[guardrails]`` table in ``.local.toml`` as a warning, not an error (§B.1).

    Example::

        >>> errors, warnings = check_hooks(SyncContext.from_repo(repo, tolerate_hook_errors=True))
        ... # doctest: +SKIP
    """
    errors = [_load_error(exc) for exc in ctx.hook_load_errors]
    errors.extend(ValidationError(v.where, v.message) for v in ctx.hook_violations)
    warnings: list[ValidationError] = []
    handlers = RegistryCatalog()  # H6/H21's registry half: in-tree map, then entry points
    check_ctx = _check_context(ctx, handlers)
    for hook in _definitions(ctx):
        _sort_into(classify_hook(hook, check_ctx), errors, warnings)
        errors.extend(_body_errors(hook))
    hooks_cfg, policy_errors = _parsed_policy(ctx)
    errors.extend(policy_errors)
    set_inputs = _set_inputs(ctx, hooks_cfg, local_policy_is_error, handlers)
    _sort_into(classify_hook_set(set_inputs), errors, warnings)
    return errors, warnings


def _sort_into(
    issues: list[HookIssue], errors: list[ValidationError], warnings: list[ValidationError]
) -> None:
    """Append each issue, as a validate finding, to the list of its severity."""
    for issue in issues:
        finding = ValidationError(path=issue.where, message=issue.message)
        (errors if issue.severity == "error" else warnings).append(finding)


def _load_error(exc: HookSchemaError) -> ValidationError:
    """``FAIL <HOOK.md>: <field>: <problem>`` for a hook that did not load (H1)."""
    return ValidationError(path=exc.where, message=str(exc).removeprefix(f"{exc.where}: "))


def _definitions(ctx: SyncContext) -> list[Hook]:
    """Every layer's definition of every hook id: each authored ``HOOK.md`` is judged."""
    if ctx.hook_definitions:
        return [hook for layer in ctx.hook_definitions.values() for hook in layer]
    return list(ctx.hooks_resolved)  # a context assembled without the resolver


def _check_context(ctx: SyncContext, handlers: HandlerCatalog) -> HookCheckContext:
    return HookCheckContext(
        engine_package=engine_package_of(ctx.artifact_source),
        rule_ids=frozenset(rule.frontmatter.id for rule in ctx.rules_resolved),
        facts=dict(ctx.facts),
        repo_root=ctx.repo_root,
        definitions=ctx.hook_definitions,
        handlers=handlers,
    )


def _body_errors(hook: Hook) -> Iterator[ValidationError]:
    """H19: the body compiles under the sandbox and never calls ``rule()``.

    A hook body renders with ``is_prompt_context=False`` (§A.8): rules are not in scope.
    """
    where = hook_location(hook)
    problem = jinja_syntax_error(hook.template_body) if hook.is_templated else None
    if problem is not None:
        yield ValidationError(where, f"Jinja syntax error: {problem}")
    if RULE_CALL_RE.search(hook.template_body):
        yield ValidationError(
            where, "body calls {{ rule(...) }} — hook bodies cannot include rules"
        )


def _parsed_policy(ctx: SyncContext) -> tuple[HooksConfig | None, list[ValidationError]]:
    """The parsed committed ``[hooks]`` (None when it does not parse) and the H21 parse errors.

    ``[guardrails]`` is parsed only to report it; the set-level rules read ``[hooks]``.
    """
    where = _config_where(ctx, FileSystemStateSource._CONFIG_FILENAME)
    errors: list[ValidationError] = []
    hooks_cfg = _parsed_or_reported(ctx.policy_tables.hooks_config, where, errors)
    _parsed_or_reported(ctx.policy_tables.guardrails_config, where, errors)
    return hooks_cfg, errors


def _parsed_or_reported[T](
    parse: Callable[[], T], where: str, errors: list[ValidationError]
) -> T | None:
    """``parse()``, or None after adding one error per line of its ``ValueError``."""
    try:
        return parse()
    except ValueError as exc:
        errors.extend(ValidationError(where, line) for line in str(exc).splitlines())
        return None


def _set_inputs(
    ctx: SyncContext,
    hooks_cfg: HooksConfig | None,
    local_policy_is_error: bool,
    handlers: HandlerCatalog,
) -> HookSetInputs:
    tables = ctx.policy_tables
    return HookSetInputs(
        hooks=ctx.hooks_resolved,
        rules=ctx.rules_resolved,
        prompt_ids=frozenset(prompt.frontmatter.id for prompt in ctx.prompts_resolved),
        hooks_cfg=hooks_cfg,
        hooks_table_present=tables.hooks is not None,
        on_hook_ids=_on_hook_ids(ctx, hooks_cfg),
        local_keys=tables.local_keys,
        overlays_enabled=tuple(ctx.config.overlays_enabled),
        engine_package=engine_package_of(ctx.artifact_source),
        config_where=_config_where(ctx, FileSystemStateSource._CONFIG_FILENAME),
        local_where=_config_where(ctx, FileSystemStateSource._CONFIG_LOCAL_FILENAME),
        local_policy_is_error=local_policy_is_error,
        handlers=handlers,
    )


def _on_hook_ids(ctx: SyncContext, hooks_cfg: HooksConfig | None) -> frozenset[str]:
    """The hooks sync would switch on (H16 judges only code that would run)."""
    if hooks_cfg is None or not hooks_cfg.enabled:
        return frozenset()
    view = resolve_effective_hooks(
        ctx.hooks_resolved,
        ctx.rules_resolved,
        hooks_cfg,
        GuardrailsConfig(),  # on or off never depends on [guardrails]
        ctx.facts,
        ctx.repo_root,
        adapters_enabled=ctx.config.adapters_enabled,
    )
    return frozenset(hook.id for hook in view.resolved)


def _config_where(ctx: SyncContext, file_name: str) -> str:
    return str(ctx.repo_root / file_name)
