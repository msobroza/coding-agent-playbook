"""The hook trust contract across hooks, artifacts and config: :func:`classify_hook_set` (prK §B.5).

The rules no single ``HOOK.md`` can decide:

- H15 (config half): ``[hooks] disable`` names no mandatory hook, and
  ``[hooks] enabled = false`` is refused while an enabled overlay ships one;
- H16: an external handler of a hook that is on comes from a source package
  listed in ``[hooks] allow_code_from`` (the engine is implicit);
- H20: no authored rule id takes the reserved advisory prefix ``guardrail-``,
  and no hook id is also a rule or prompt id (``playbook render`` looks ids up
  across kinds);
- H21: ``enable``/``disable`` name existing hooks and are disjoint;
  ``allow_code_from`` ⊆ ``overlays_enabled`` + ``<repo-local>``; no
  ``wrapper_prefixes`` entry hides a guarded command
  (``hook_runtime.wrapper_policy``, the rule the dispatcher applies to
  ``PLAYBOOK_HOOK_WRAPPER_PREFIXES``); every ``[hooks.<x>]`` names a hook;
  ``[hooks.stop-ci-parity-gate] stages`` ⊆ {``typecheck``, ``tests``}; and
  neither policy table sits in ``.local.toml`` (an error for validate, a
  warning for sync, §B.1).

That the tables parse at all (unknown keys, types, ``cutover_date``) is the
parser's ``ValueError``, reported by the caller; checking ``[hooks.<x>]``
against the handler's ``CONFIG_SCHEMA`` is the registry half (``handler_catalog``). Without a
consumer config every input is empty, so H15/H16/H21 find nothing (P8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE, REPO_LOCAL_SOURCE
from coding_agent_playbook.hook_policy._contract_handlers import handler_slots
from coding_agent_playbook.hook_policy._findings import (
    HookIssue,
    Severity,
    did_you_mean,
    hook_location,
)
from coding_agent_playbook.hook_policy.handler_catalog import config_findings
from coding_agent_playbook.hook_policy.tables import ADVISORY_RULE_PREFIX
from coding_agent_playbook.hook_runtime.wrapper_policy import hidden_program

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from coding_agent_playbook.config.tables.hooks import HooksConfig
    from coding_agent_playbook.hook_policy.handler_catalog import HandlerCatalog
    from coding_agent_playbook.types import Hook, Rule

#: The stages ``[hooks.stop-ci-parity-gate] stages`` may enable (§B.1): the two
#: that run repo-controlled code, so trust-gated (§B.4).
STOP_GATE_STAGES: Final = ("typecheck", "tests")
_STOP_GATE: Final = "stop-ci-parity-gate"


def _committed_config_name() -> str:
    """``CONFIG_FILENAME``, imported on use: importing hook_policy loads no config module."""
    from coding_agent_playbook.config.files import CONFIG_FILENAME

    return CONFIG_FILENAME


def _local_config_name() -> str:
    """``CONFIG_LOCAL_FILENAME``, imported on use, like :func:`_committed_config_name`."""
    from coding_agent_playbook.config.files import CONFIG_LOCAL_FILENAME

    return CONFIG_LOCAL_FILENAME


@dataclass(frozen=True)
class HookSetInputs:
    """What :func:`classify_hook_set` judges; every field defaults to "nothing there".

    ``hooks`` and ``rules`` are the merged sets. ``hooks_cfg`` is the parsed
    committed ``[hooks]`` (None when it did not parse: that is reported on its
    own); ``hooks_table_present`` tells an explicit ``[hooks]`` from an absent
    one. ``on_hook_ids`` are the hooks the effective view switched on (H16).
    ``local_keys`` are the ``.local.toml`` policy keys sync ignored.
    ``handlers`` checks each ``[hooks.<id>]`` against its handlers'
    ``CONFIG_SCHEMA`` (``None``: skipped).
    ``config_where`` / ``local_where`` locate config findings.

    Example::

        >>> classify_hook_set(HookSetInputs())
        []
    """

    hooks: Sequence[Hook] = ()
    rules: Sequence[Rule] = ()
    prompt_ids: frozenset[str] = frozenset()
    hooks_cfg: HooksConfig | None = None
    hooks_table_present: bool = False
    on_hook_ids: frozenset[str] = frozenset()
    local_keys: tuple[str, ...] = ()
    overlays_enabled: tuple[str, ...] = ()
    engine_package: str = ENGINE_PACKAGE
    # Factories, not the constants: hook_policy stays import-light (its stdlib-only
    # import probe), so config.files loads only when a default is needed.
    config_where: str = field(default_factory=_committed_config_name)
    local_where: str = field(default_factory=_local_config_name)
    local_policy_is_error: bool = True
    handlers: HandlerCatalog | None = None


def classify_hook_set(inputs: HookSetInputs) -> list[HookIssue]:
    """Every H15 (config), H16, H20 and H21 finding of ``inputs``; never raises.

    Example::

        >>> classify_hook_set(HookSetInputs(hooks_cfg=parse_hooks_config({"disable": ["x"]})))
        ... # doctest: +SKIP
        [HookIssue(severity='error', where='.coding-agent-playbook.toml',
                   message="[hooks] disable: unknown hook id 'x'")]
    """
    return [
        *_reserved_rule_ids(inputs),
        *_id_clashes(inputs),
        *_mandatory_switches(inputs),
        *_code_sources(inputs),
        *_hooks_table(inputs),
        *_local_policy(inputs),
    ]


def _config_error(inputs: HookSetInputs, message: str) -> HookIssue:
    return HookIssue("error", inputs.config_where, message)


def _reserved_rule_ids(inputs: HookSetInputs) -> Iterator[HookIssue]:
    """H20: ``guardrail-<hook-id>`` is the advisory rule a hook degrades to (§A.8)."""
    for rule in inputs.rules:
        rule_id = rule.frontmatter.id
        if rule_id.startswith(ADVISORY_RULE_PREFIX):
            where = str(rule.source_path or f"rules/{rule_id} ({rule.source_package})")
            message = f"rule id {rule_id!r} uses the reserved {ADVISORY_RULE_PREFIX!r} prefix"
            yield HookIssue("error", where, message)


def _id_clashes(inputs: HookSetInputs) -> Iterator[HookIssue]:
    """H20: a hook id that is also a rule or prompt id makes ``playbook render <id>`` ambiguous."""
    rule_ids = {rule.frontmatter.id for rule in inputs.rules}
    for hook in inputs.hooks:
        hook_id = hook.frontmatter.id
        for kind, ids in (("rule", rule_ids), ("prompt", inputs.prompt_ids)):
            if hook_id in ids:
                yield HookIssue(
                    "error",
                    hook_location(hook),
                    f"hook id {hook_id!r} is also a {kind} id; playbook render looks ids up "
                    "across kinds, so rename one",
                )


def _mandatory_switches(inputs: HookSetInputs) -> Iterator[HookIssue]:
    """H15: mandatory hooks cannot be disabled, nor all hooks switched off around them."""
    cfg = inputs.hooks_cfg
    if cfg is None:
        return
    mandatory = {hook.frontmatter.id: hook for hook in inputs.hooks if hook.frontmatter.mandatory}
    for hook_id in dict.fromkeys(cfg.disable):
        if hook_id in mandatory:
            owner = mandatory[hook_id].source_package
            yield _config_error(
                inputs,
                f"[hooks] disable: {hook_id!r} is mandatory (overlay {owner}) and cannot be disabled",
            )
    if not inputs.hooks_table_present or cfg.enabled:
        return  # an absent table is the no-upgrade-drift default, not an opt-out (§B.1)
    for hook_id, hook in mandatory.items():
        if hook.source_package in inputs.overlays_enabled:
            yield _config_error(
                inputs,
                f"[hooks] enabled = false while overlay {hook.source_package!r} ships mandatory "
                f"hook {hook_id!r}; mandatory hooks cannot be switched off: set enabled = true",
            )


def _code_sources(inputs: HookSetInputs) -> Iterator[HookIssue]:
    """H16: only an on hook runs code, and only from a source the consumer allowed."""
    cfg = inputs.hooks_cfg
    if cfg is None:
        return
    allowed = {*cfg.allow_code_from, inputs.engine_package}
    for hook in inputs.hooks:
        fm = hook.frontmatter
        if fm.id not in inputs.on_hook_ids or hook.source_package in allowed:
            continue
        if any(handler.builtin is None for _, handler in handler_slots(fm)):
            yield HookIssue(
                "error",
                hook_location(hook),
                f"hook {fm.id!r} runs code from {hook.source_package!r}; "
                "add it to [hooks] allow_code_from",
            )


def _hooks_table(inputs: HookSetInputs) -> Iterator[HookIssue]:
    """H21: the ``[hooks]`` table refers only to things that exist."""
    cfg = inputs.hooks_cfg
    if cfg is None:
        return
    hook_ids = [hook.frontmatter.id for hook in inputs.hooks]
    for key, ids in (("enable", cfg.enable), ("disable", cfg.disable)):
        for hook_id in dict.fromkeys(ids):
            if hook_id not in hook_ids:
                hint = did_you_mean(hook_id, hook_ids)
                yield _config_error(inputs, f"[hooks] {key}: unknown hook id {hook_id!r}{hint}")
    for hook_id in dict.fromkeys(cfg.enable):
        if hook_id in cfg.disable:
            yield _config_error(
                inputs,
                f"[hooks] enable and disable both name {hook_id!r}; disable wins, "
                "so list it in one of them only",
            )
    yield from _code_source_names(inputs, cfg)
    yield from _hiding_wrappers(inputs, cfg)
    for table in cfg.per_hook:
        if table not in hook_ids:
            hint = did_you_mean(table, hook_ids)
            yield _config_error(inputs, f"[hooks.{table}]: unknown hook id {table!r}{hint}")
    yield from _stop_gate_stages(inputs, cfg)
    if inputs.handlers is not None:  # the CONFIG_SCHEMA half (K2's registry)
        for finding in config_findings(inputs.hooks, cfg.per_hook, inputs.handlers):
            yield HookIssue(finding.severity, inputs.config_where, finding.message)


def _code_source_names(inputs: HookSetInputs, cfg: HooksConfig) -> Iterator[HookIssue]:
    allowed = (*inputs.overlays_enabled, REPO_LOCAL_SOURCE)
    for source in dict.fromkeys(cfg.allow_code_from):
        if source not in allowed:
            yield _config_error(
                inputs,
                f"[hooks] allow_code_from: {source!r} is neither an enabled overlay nor "
                f"{REPO_LOCAL_SOURCE!r}; allowed: {', '.join(allowed)}",
            )


def _hiding_wrappers(inputs: HookSetInputs, cfg: HooksConfig) -> Iterator[HookIssue]:
    """A declared wrapper is stripped before every shell guard, so it must not be a guarded command."""
    for prefix in dict.fromkeys(cfg.wrapper_prefixes):
        hidden = hidden_program(prefix)
        if hidden is not None:
            yield _config_error(
                inputs,
                f"[hooks] wrapper_prefixes: {prefix!r} would hide {hidden!r} from every shell "
                "guard; declare only a launcher that is not itself a guarded command "
                "(e.g. 'proxy')",
            )


def _stop_gate_stages(inputs: HookSetInputs, cfg: HooksConfig) -> Iterator[HookIssue]:
    stages = cfg.per_hook.get(_STOP_GATE, {}).get("stages")
    if stages is None:
        return
    if isinstance(stages, list) and all(stage in STOP_GATE_STAGES for stage in stages):
        return
    allowed = ", ".join(repr(stage) for stage in STOP_GATE_STAGES)
    yield _config_error(
        inputs, f"[hooks.{_STOP_GATE}] stages: must be a list drawn from {allowed}, got {stages!r}"
    )


def _local_policy(inputs: HookSetInputs) -> Iterator[HookIssue]:
    """H21 / §B.1: policy keys in ``.local.toml`` are ignored; validate errs, sync warns."""
    if not inputs.local_keys:
        return
    severity: Severity = "error" if inputs.local_policy_is_error else "warning"
    yield HookIssue(
        severity,
        inputs.local_where,
        f"{', '.join(inputs.local_keys)}: [hooks] and [guardrails] are read from the "
        "committed config only, so these local values are ignored; move them to the "
        "committed config or delete them",
    )
