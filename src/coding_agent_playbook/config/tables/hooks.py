"""Parse the ``[hooks]`` and ``[guardrails]`` tables (specs/prK-lifecycle-hooks.md §B.1, §B.3).

``[hooks]`` is mechanism: which hooks render and how. ``[guardrails]`` is policy
data shared with the hooks' off-workstation twins, so it applies even with hooks
off. Both parsers are pure (a decoded TOML table in, a frozen dataclass out) and
raise one ``ValueError`` naming every offending value and its expected shape.

Both tables are read from the committed ``.coding-agent-playbook.toml`` only:
:func:`policy_tables` drops them from ``.coding-agent-playbook.local.toml`` and
records what it dropped, because committed output must not depend on a
gitignored file CI never sees (§B.1). Read hooks policy through
:class:`PolicyTables`, never through ``Config.extra_tables``, which holds the
deep-merged view. Split out of ``config.py`` (now ``config/model.py``) for its
size budget; stdlib-only.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.config.tables._table_shapes import (
    BOOL,
    ISO_DATE_TEXT,
    POSITIVE_INT,
    STRINGS,
    TEXT,
    TableShape,
    one_of,
    read_table,
    shape_problem,
    subset_of,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

UnattendedAsk = Literal["deny", "warn"]
NetworkMode = Literal["off", "ask", "enforce"]
StopSweepMode = Literal["block", "warn", "off"]

#: The top-level tables ``.coding-agent-playbook.local.toml`` may never carry (§B.1).
POLICY_TABLE_NAMES: Final = ("hooks", "guardrails")

#: The one ``[hooks]`` sub-table that is not a hook id (addendum D-Q3, lock K-4).
COMMIT_CONVENTION_TABLE: Final = "commit_convention"

DEFAULT_PROTECTED_BRANCHES: Final = ("main", "master", "release/*")

_HOOKS_SHAPES: Final[Mapping[str, TableShape]] = {
    "enabled": BOOL,
    "adapters": STRINGS,
    "tiers": subset_of(
        "default",
        "opt-in",
        note="an overlay-tier hook is activated only by an overlay promoting it to tier: default",
    ),
    "enable": STRINGS,
    "disable": STRINGS,
    "advisory": BOOL,
    "unattended_ask": one_of("deny", "warn"),
    "allow_code_from": STRINGS,
    "auto_sync": BOOL,
    "wrapper_prefixes": STRINGS,
    "state_ttl_days": POSITIVE_INT,
    "render_remediation_allow": BOOL,
}

_COMMIT_CONVENTION_SHAPES: Final[Mapping[str, TableShape]] = {"cutover_date": ISO_DATE_TEXT}


@dataclass(frozen=True)
class CommitConventionConfig:
    """``[hooks.commit_convention]``: the committer-date cut-over of range checks (D-Q3).

    ``cutover_date`` is a ``"YYYY-MM-DD"`` string; ``None`` checks every commit.

    Example::

        >>> parse_hooks_config({"commit_convention": {"cutover_date": "2026-10-15"}}).commit_convention
        CommitConventionConfig(cutover_date='2026-10-15')
    """

    cutover_date: str | None = None


@dataclass(frozen=True)
class HooksConfig:
    """The ``[hooks]`` table (§B.1); off unless ``enabled`` is written ``true``.

    ``adapters`` is ``None`` when unset, meaning ``adapters_enabled ∩ {claude_code,
    opencode}`` (resolved by ``hooks.resolution.effective.resolve_effective_hooks``).
    ``per_hook`` holds each ``[hooks.<hook-id>]`` sub-table verbatim: the consumer layer of that
    hook's ``handler.config`` (lock K-4), checked against the handler's
    ``CONFIG_SCHEMA`` by validate (H21).

    Example::

        >>> parse_hooks_config({"enabled": True}).tiers
        ('default',)
    """

    enabled: bool = False
    adapters: tuple[str, ...] | None = None
    tiers: tuple[str, ...] = ("default",)
    enable: tuple[str, ...] = ()
    disable: tuple[str, ...] = ()
    advisory: bool = True
    unattended_ask: UnattendedAsk = "deny"
    allow_code_from: tuple[str, ...] = ()
    auto_sync: bool = False
    wrapper_prefixes: tuple[str, ...] = ()
    state_ttl_days: int = 7
    render_remediation_allow: bool = False
    per_hook: dict[str, dict[str, Any]] = field(default_factory=dict)
    commit_convention: CommitConventionConfig = field(default_factory=CommitConventionConfig)


@dataclass(frozen=True)
class SecretsGuardrails:
    """``[guardrails.secrets]``: globs added to SECRET_PATH_GLOBS (extend), fixture exemptions (relax)."""

    extra_globs: tuple[str, ...] = ()
    allow_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class GitGuardrails:
    """``[guardrails.git]``: branches no agent may force-push to (extend)."""

    protected_branches: tuple[str, ...] = DEFAULT_PROTECTED_BRANCHES


@dataclass(frozen=True)
class NetworkGuardrails:
    """``[guardrails.network]``: network-egress-guard's mode (strictest) and hosts (relax)."""

    mode: NetworkMode = "off"
    allowed_hosts: tuple[str, ...] = ()


@dataclass(frozen=True)
class DependenciesGuardrails:
    """``[guardrails.dependencies]``: dependency-allowlist-guard; its mode values are §E.4's."""

    mode: str | None = None
    allowlist: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditGuardrails:
    """``[guardrails.audit]``: local-audit-log retention; ``None`` keeps the handler's default."""

    retain_days: int | None = None


@dataclass(frozen=True)
class StopSweepGuardrails:
    """``[guardrails.stop_sweep]``: stop-diff-sweep's mode (strictest)."""

    mode: StopSweepMode = "block"


#: Domain -> its dataclass and key shapes; the merge policy of each key is the
#: handler's own (CONFIG_SCHEMA), applied by
#: hooks.resolution.effective.resolve_effective_hooks.
_GUARDRAIL_DOMAINS: Final[Mapping[str, tuple[type[Any], Mapping[str, TableShape]]]] = {
    "secrets": (SecretsGuardrails, {"extra_globs": STRINGS, "allow_paths": STRINGS}),
    "git": (GitGuardrails, {"protected_branches": STRINGS}),
    "network": (
        NetworkGuardrails,
        {"mode": one_of("off", "ask", "enforce"), "allowed_hosts": STRINGS},
    ),
    "dependencies": (DependenciesGuardrails, {"mode": TEXT, "allowlist": STRINGS}),
    "audit": (AuditGuardrails, {"retain_days": POSITIVE_INT}),
    "stop_sweep": (StopSweepGuardrails, {"mode": one_of("block", "warn", "off")}),
}


@dataclass(frozen=True)
class GuardrailsConfig:
    """The ``[guardrails]`` table (§B.3): one dataclass per policy domain, defaults filled in.

    ``explicit`` maps each domain the consumer wrote to the keys it set: only
    those merge into a builtin handler's config (:meth:`domain_values`), so a
    default never overrides a value an engine or overlay layer chose.

    Example::

        >>> parse_guardrails_config(None).git.protected_branches
        ('main', 'master', 'release/*')
    """

    secrets: SecretsGuardrails = field(default_factory=SecretsGuardrails)
    git: GitGuardrails = field(default_factory=GitGuardrails)
    network: NetworkGuardrails = field(default_factory=NetworkGuardrails)
    dependencies: DependenciesGuardrails = field(default_factory=DependenciesGuardrails)
    audit: AuditGuardrails = field(default_factory=AuditGuardrails)
    stop_sweep: StopSweepGuardrails = field(default_factory=StopSweepGuardrails)
    explicit: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def domain_values(self, domain: str) -> dict[str, Any]:
        """The keys the consumer set in ``[guardrails.<domain>]``, lists as lists.

        Example::

            >>> parse_guardrails_config({"git": {"protected_branches": ["dev"]}}).domain_values("git")
            {'protected_branches': ['dev']}
        """
        keys = self.explicit.get(domain, ())
        section = getattr(self, domain, None)
        return {key: _plain(getattr(section, key)) for key in keys}


@dataclass(frozen=True)
class PolicyTables:
    """The committed ``[hooks]`` / ``[guardrails]`` tables, kept raw, and the ignored local keys.

    Raw, so building a context never dies on a malformed table: :meth:`hooks_config`
    and :meth:`guardrails_config` parse on demand and raise the ``ValueError``
    validate reports as H21. ``local_keys`` are the dotted ``.local.toml`` keys
    the §B.1 exclusion ignored (sync warns; validate errors, H21).

    Example::

        >>> PolicyTables().hooks_config().enabled
        False
    """

    hooks: Any = None
    guardrails: Any = None
    local_keys: tuple[str, ...] = ()

    def hooks_config(self) -> HooksConfig:
        """:func:`parse_hooks_config` of the committed ``[hooks]`` table."""
        return parse_hooks_config(self.hooks)

    def guardrails_config(self) -> GuardrailsConfig:
        """:func:`parse_guardrails_config` of the committed ``[guardrails]`` table."""
        return parse_guardrails_config(self.guardrails)


def parse_hooks_config(data: object) -> HooksConfig:
    """Parse a ``[hooks]`` table (``None`` = absent) into a :class:`HooksConfig`.

    A key holding a table is a ``[hooks.<hook-id>]`` consumer layer, except the
    reserved ``[hooks.commit_convention]``. Raises ``ValueError`` listing every
    unknown key and wrong type, each with the value and the expected shape.

    Example::

        >>> parse_hooks_config({"enabled": True, "disable": ["guard-x"]}).disable
        ('guard-x',)
    """
    if data is None:
        return HooksConfig()
    scalars, sub_tables = _split_hooks_table(_require_table(data, "[hooks]"))
    problems: list[str] = []
    values = read_table(
        scalars,
        _HOOKS_SHAPES,
        label="[hooks]",
        problems=problems,
        also_allowed="a [hooks.<hook-id>] table",
    )
    convention = _commit_convention(sub_tables.pop(COMMIT_CONVENTION_TABLE, None), problems)
    _raise_problems(problems)
    return HooksConfig(**values, per_hook=copy.deepcopy(sub_tables), commit_convention=convention)


def parse_guardrails_config(data: object) -> GuardrailsConfig:
    """Parse a ``[guardrails]`` table (``None`` = absent) into a :class:`GuardrailsConfig`.

    Raises ``ValueError`` listing every unknown domain or key and every wrong
    value, each with the value and the expected shape.

    Example::

        >>> parse_guardrails_config({"network": {"mode": "ask"}}).network.mode
        'ask'
    """
    if data is None:
        return GuardrailsConfig()
    problems: list[str] = []
    sections: dict[str, Any] = {}
    explicit: dict[str, tuple[str, ...]] = {}
    for domain, value in _require_table(data, "[guardrails]").items():
        values = _read_domain(domain, value, problems)
        if values is not None:
            sections[domain] = _GUARDRAIL_DOMAINS[domain][0](**values)
            explicit[domain] = tuple(values)
    _raise_problems(problems)
    return GuardrailsConfig(**sections, explicit=explicit)


def policy_tables(committed: Mapping[str, Any], local: Mapping[str, Any]) -> PolicyTables:
    """The policy tables of the ``committed`` config table; ``local``'s are only recorded.

    ``committed`` is the committed file's top level (or its ``Config.extra_tables``),
    ``local`` the ``.local.toml`` table. The raw tables are deep-copied.

    Example::

        >>> policy_tables({"hooks": {"enabled": True}}, {"hooks": {"enabled": False}}).local_keys
        ('hooks.enabled',)
    """
    local_keys = tuple(
        path
        for name in POLICY_TABLE_NAMES
        if name in local
        for path in _leaf_paths(local[name], (name,))
    )
    return PolicyTables(
        hooks=copy.deepcopy(committed.get("hooks")),
        guardrails=copy.deepcopy(committed.get("guardrails")),
        local_keys=local_keys,
    )


def _split_hooks_table(table: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(scalar keys, sub-tables)``: a table under a non-scalar key is a sub-table."""
    scalars: dict[str, Any] = {}
    sub_tables: dict[str, Any] = {}
    for key, value in table.items():
        is_sub_table = key == COMMIT_CONVENTION_TABLE or (
            key not in _HOOKS_SHAPES and isinstance(value, dict)
        )
        (sub_tables if is_sub_table else scalars)[key] = value
    return scalars, sub_tables


def _commit_convention(value: object, problems: list[str]) -> CommitConventionConfig:
    if value is None:
        return CommitConventionConfig()
    if not isinstance(value, dict):
        problems.append(shape_problem("[hooks]", COMMIT_CONVENTION_TABLE, "a table", value))
        return CommitConventionConfig()
    label = f"[hooks.{COMMIT_CONVENTION_TABLE}]"
    values = read_table(value, _COMMIT_CONVENTION_SHAPES, label=label, problems=problems)
    return CommitConventionConfig(**values)


def _read_domain(domain: str, value: object, problems: list[str]) -> dict[str, Any] | None:
    """The checked keys of ``[guardrails.<domain>]``; ``None`` when the domain itself is wrong."""
    if domain not in _GUARDRAIL_DOMAINS:
        allowed = ", ".join(sorted(_GUARDRAIL_DOMAINS))
        problems.append(f"[guardrails] unknown domain {domain!r}; allowed: {allowed}")
        return None
    if not isinstance(value, dict):
        problems.append(shape_problem("[guardrails]", domain, "a table", value))
        return None
    shapes = _GUARDRAIL_DOMAINS[domain][1]
    return read_table(value, shapes, label=f"[guardrails.{domain}]", problems=problems)


def _require_table(data: object, label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a table, got {data!r}")
    return data


def _raise_problems(problems: list[str]) -> None:
    if problems:
        raise ValueError("\n".join(problems))


def _leaf_paths(value: object, path: tuple[str, ...]) -> Iterator[str]:
    """Every dotted key path under ``value``; an empty table is reported as itself."""
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from _leaf_paths(child, (*path, key))
    else:
        yield ".".join(path)


def _plain(value: object) -> object:
    """A stored tuple back as the list TOML (and handler config) would hold."""
    return list(value) if isinstance(value, tuple) else value
