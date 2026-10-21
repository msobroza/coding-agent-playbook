"""``SyncContext``, and the context ``playbook validate`` builds without a consumer config.

:class:`SyncContext` is the bundle of (config, facts, source, adapters, resolved
artifacts) handed to every command that reads the catalog: ``sync``, ``validate``,
``check``, ``render`` and ``eval``. It lives here, below sync, because validation
and those commands import it (H4; split out of the sync orchestration module in A5,
specs/prT-package-layout.md 4.5). Its invariants (PR 10):

- adapters are never instantiated directly; :func:`discover_adapters` loads them
  through ``[project.entry-points."coding_agent_playbook.adapters"]``;
- ``rules_resolved`` etc. are post-overlay-merge but pre-applies_if-filter.
  Filtering happens inside the commands so each command can pick its own
  semantics (sync filters; render does not; check shows both sides).

Config-less validate (prK §P P8a): an engine or overlay checkout has no
``.coding-agent-playbook.toml``, so
:meth:`SyncContext.from_repo` raised :class:`FileNotFoundError` there and
overlay authors could not validate their own artifacts. Config-less validate
walks three layers instead:

- the engine (its bundled ``catalog/core/``);
- the checkout's own ``<root>/src/<pkg>/resources/`` (an overlay checkout),
  minus the engine package's own ``resources/``: the engine ships its content
  in ``catalog/`` since v0.19, but a checkout whose ``src/<pkg>`` resolves to an
  engine package with a ``resources/`` tree would otherwise walk it twice;
- ``<root>/playbook/``.

Installed overlays are not discovered: overlays resolve by package name from
``overlays_enabled`` only, and the ``coding_agent_playbook.overlays`` entry-point
group has no defined value shape to invent one from. Checks that read the
consumer config are skipped and named (:data:`CONSUMER_CONFIG_CHECKS`).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook import __version__
from coding_agent_playbook.adapters.registry import discover_adapters
from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.catalog.resolve import OverlayResolver
from coding_agent_playbook.catalog.roots import canonical_overlay_name
from coding_agent_playbook.catalog.source import FileSystemArtifactSource, engine_package_of
from coding_agent_playbook.config.files import CONFIG_FILENAME, ConfigFiles, FileSystemStateSource
from coding_agent_playbook.config.model import Config, ProjectMeta
from coding_agent_playbook.config.tables.hooks import PolicyTables
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.hooks.contract.handler_catalog import RegistryCatalog
from coding_agent_playbook.hooks.resolution.merge import split_hook_layers

if TYPE_CHECKING:
    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule, RuleLoadError
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.catalog.resolve import Collision
    from coding_agent_playbook.catalog.source import ArtifactSource
    from coding_agent_playbook.config.files import StateSource
    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.hooks.resolution.merge import HookViolation
    from coding_agent_playbook.rendering.rule_registry import RuleRegistry

#: The checks config-less validate skips, one note line each. The hook policy
#: rules need the consumer's [hooks] table, which a config-less context has none of.
CONSUMER_CONFIG_CHECKS: Final = (
    "overlays_enabled usability (no overlay list to check)",
    "[links] allowed_domains (no allowlist to read; external links fail the strict default)",
    "[hooks] / [guardrails] policy: H15 switches, H16 allow_code_from, H21 tables "
    "(no consumer config to read)",
)

# The stand-in project kind: the detector's own fallback for an unknown project.
_CONFIG_LESS_KIND = "python-unknown"


def has_consumer_config(repo_root: Path) -> bool:
    """True when ``repo_root`` holds the committed ``.coding-agent-playbook.toml``.

    Example::

        >>> has_consumer_config(Path("/no/such/repo"))
        False
    """
    return ConfigFiles(repo_root).has_committed()


def config_less_notes(repo_root: Path) -> list[str]:
    """The lines validate prints before its result when there is no consumer config.

    Example::

        >>> config_less_notes(Path("/repo"))[1]
        'skipped: overlays_enabled usability (no overlay list to check)'
    """
    return [
        f"note: no {CONFIG_FILENAME} in {repo_root}; validating the "
        "engine package, src/*/resources/ and playbook/ only",
        *(f"skipped: {check}" for check in CONSUMER_CONFIG_CHECKS),
    ]


def checkout_resource_roots(repo_root: Path, *, engine_package: str) -> list[Path]:
    """Every ``<repo_root>/src/<pkg>/resources/`` dir except ``engine_package``'s own.

    Deduplicated by resolved path, so the engine checkout (an editable install,
    or a symlink to the installed package) never doubles the engine layer.
    Dot-directories are skipped, like every other artifact walk.

    Example::

        >>> checkout_resource_roots(Path("/no/such/repo"), engine_package="coding_agent_playbook")
        []
    """
    src = repo_root / "src"
    if not src.is_dir():
        return []
    engine = _resolved_resources_dir(engine_package)
    return [
        root
        for root in sorted(src.glob("*/resources"))
        if root.is_dir() and not root.parent.name.startswith(".") and root.resolve() != engine
    ]


def _resolved_resources_dir(package: str) -> Path | None:
    """``<package>/resources`` resolved, or ``None`` when the package cannot import."""
    try:
        return Path(str(resources.files(package).joinpath("resources"))).resolve()
    except Exception:
        # Like catalog.source._resource_subdir: an import may raise anything.
        return None


def config_less_context(repo_root: Path) -> SyncContext:
    """The :class:`SyncContext` validate uses when ``repo_root`` has no consumer config.

    A stand-in :class:`Config` with no overlays and no adapters beyond the
    always-on ``agents_md``; the artifact source adds the checkout's own
    ``src/*/resources/`` layers. A malformed hook is recorded, not raised (P8c).

    Example::

        >>> config_less_context(Path("/path/to/overlay-checkout")).rules_resolved  # doctest: +SKIP
        [Rule(...), ...]
    """
    source = FileSystemArtifactSource(
        repo_root=repo_root,
        extra_resource_roots=checkout_resource_roots(repo_root, engine_package=ENGINE_PACKAGE),
    )
    return SyncContext.from_config(
        repo_root, _config_less_config(repo_root), artifact_source=source, tolerate_load_errors=True
    )


def _config_less_config(repo_root: Path) -> Config:
    """A consumer config as ``playbook init`` would start one, with nothing enabled."""
    return Config(
        schema_version=1,
        project=ProjectMeta(name=repo_root.resolve().name, kind=_CONFIG_LESS_KIND),
        engine_version=__version__,
    )


def _warn_deprecated_overlays(config: Config, state: FileSystemStateSource) -> None:
    """Print one stderr ``warning:`` per distinct deprecated overlay name (SPEC v0.19).

    The line names the file to fix: the local file when it sets
    ``overlays_enabled`` (lists replace whole in the SPEC §7.2 merge), else the
    committed one. A print, not ``warnings.warn``: CLI users never see a
    ``DeprecationWarning``, and pytest runs with ``filterwarnings = error``.
    Called only from :meth:`SyncContext.from_repo`, so a directly built
    ``SyncContext`` (or ``Config``) stays silent.

    Example::

        >>> _warn_deprecated_overlays(config, state)  # doctest: +SKIP
        warning: <file>: overlays_enabled: '<old>' is deprecated; use '<new>'
    """
    if not config.deprecated_overlay_names:
        return
    local_sets_list = "overlays_enabled" in state.load_local_overrides()
    source = state._CONFIG_LOCAL_FILENAME if local_sets_list else state._CONFIG_FILENAME
    # Listed twice, a name is walked twice (canonical_overlay_list keeps it), but warned once.
    for old in dict.fromkeys(config.deprecated_overlay_names):
        print(
            f"warning: {source}: overlays_enabled: '{old}' is deprecated; "
            f"use '{canonical_overlay_name(old)}'",
            file=sys.stderr,
        )


@dataclass
class SyncContext:
    """Bundle of state every CLI command needs after reading the config.

    ``rules_resolved``, ``prompts_resolved``, ``skills_resolved`` and
    ``hooks_resolved`` are post-overlay-merge but pre-applies_if-filter —
    filtering is the command's responsibility (sync filters; render does not).
    ``rule_definitions`` is every layer's well-formed rule, pre-merge (read it,
    never ``artifact_source.list_rules()``, which raises on a malformed file).
    ``hook_load_errors`` and ``rule_load_errors`` hold the malformed hooks and
    rule files that ``tolerate_load_errors`` set aside (prU D21);
    ``hook_violations`` the refused layer overrides (prK §A.5, §A.6).
    ``policy_tables`` holds the committed ``[hooks]`` / ``[guardrails]`` tables,
    raw so validate can report a malformed one (H21); read hooks policy there,
    never from ``config.extra_tables``, which merges ``.local.toml`` in (§B.1).
    """

    repo_root: Path
    config: Config
    facts: Facts
    artifact_source: ArtifactSource
    state_source: StateSource
    adapters: dict[str, Adapter] = field(default_factory=dict)
    rules_resolved: list[Rule] = field(default_factory=list)
    prompts_resolved: list[Prompt] = field(default_factory=list)
    skills_resolved: list[Skill] = field(default_factory=list)
    overlay_collisions: list[Collision] = field(default_factory=list)
    hooks_resolved: list[Hook] = field(default_factory=list)
    hook_definitions: dict[str, tuple[Hook, ...]] = field(default_factory=dict)
    hook_load_errors: list[HookSchemaError] = field(default_factory=list)
    rule_definitions: list[Rule] = field(default_factory=list)
    rule_load_errors: list[RuleLoadError] = field(default_factory=list)
    hook_violations: list[HookViolation] = field(default_factory=list)
    policy_tables: PolicyTables = field(default_factory=PolicyTables)

    @classmethod
    def from_repo(
        cls,
        repo_root: Path,
        *,
        rule_registry: RuleRegistry | None = None,
        tolerate_load_errors: bool = False,
        warn_deprecated: bool = True,
    ) -> SyncContext:
        """Discovery: load config → detect facts → instantiate sources → resolve overlays.

        ``rule_registry`` is optional because the adapters need it but the
        registry itself depends on the filtered rule list, which depends on
        facts. Callers that want the full pipeline build the context once
        without a registry, then re-build the adapters via
        :func:`discover_adapters` after the registry exists.

        A malformed hook raises ``HookSchemaError`` and a malformed rule file
        ``RuleLoadError`` (sync, check, render and eval fail loudly);
        ``tolerate_load_errors=True`` records each one on ``hook_load_errors`` /
        ``rule_load_errors`` instead, so ``playbook validate`` can report them
        all (prK §P P8c, prU D21).

        Prints one ``warning:`` line per deprecated ``coding_agent_playbook.packs.*``
        overlay name, before anything else runs (:func:`_warn_deprecated_overlays`).
        ``warn_deprecated=False`` is for an internal re-read inside a command that
        already built its own context (the hook twins' policy read during
        ``init``), so the user sees each warning once.
        """
        state_source = FileSystemStateSource(repo_root=repo_root)
        config = state_source.load_config()
        if warn_deprecated:
            _warn_deprecated_overlays(config, state_source)
        return cls.from_config(
            repo_root,
            config,
            rule_registry=rule_registry,
            tolerate_load_errors=tolerate_load_errors,
            policy_tables=state_source.load_policy_tables(),
        )

    @classmethod
    def from_config(
        cls,
        repo_root: Path,
        config: Config,
        *,
        artifact_source: ArtifactSource | None = None,
        rule_registry: RuleRegistry | None = None,
        tolerate_load_errors: bool = False,
        policy_tables: PolicyTables | None = None,
    ) -> SyncContext:
        """:meth:`from_repo` minus the config load: detect → walk → resolve overlays.

        Config-less ``playbook validate`` passes a stand-in ``config`` and an
        ``artifact_source`` with extra checkout layers (prK §P P8); by default
        the source walks the engine, ``config.layers_enabled`` (the framework, then the overlays) and
        ``<repo>/playbook/``. Without ``policy_tables`` there is no ``[hooks]``
        table, so hooks are off.

        Example::

            >>> SyncContext.from_config(repo, config).rules_resolved  # doctest: +SKIP
            [Rule(...), ...]
        """
        facts = detect(repo_root)
        if artifact_source is None:
            artifact_source = FileSystemArtifactSource(
                repo_root=repo_root,
                overlay_packages=config.layers_enabled,
            )
        # FileSystemArtifactSource walks the engine and bundled-plugin artifacts
        # in the catalog (``catalog/core/``, ``catalog/plugins/<name>/``)
        # and each overlay package's ``resources/`` tree via importlib.resources;
        # repo-local artifacts come from ``<repo>/playbook/``. v1 walks all of
        # those in a single ``list_*`` call — sufficient for PR 10. PRs 13+
        # may split per-layer if we need fine-grained source provenance.
        resolver = OverlayResolver(hook_schemas=RegistryCatalog())  # handlers' CONFIG_SCHEMA
        all_rules, rule_load_errors = (
            artifact_source.collect_rules()
            if tolerate_load_errors
            else (artifact_source.list_rules(), [])
        )
        all_prompts = artifact_source.list_prompts()
        all_skills = artifact_source.list_skills()
        # TODO(PR-13): the OverlayResolver supports per-layer wiring
        # (engine, overlays, repo-local) for the three-layer merge in
        # SPEC §11, but ``FileSystemArtifactSource`` currently returns a
        # single flattened list across all sources.
        # v1: source already flattened; per-layer wiring lands when the first
        # overlay package needs it. See SPEC §11 for layer order.
        # ID collisions across the merged list still flag winners vs losers
        # via insertion-order semantics, which is enough for the engine-only
        # v1 we ship today.
        rules_resolved = resolver.resolve_rules(all_rules, [], [])
        prompts_resolved = resolver.resolve_prompts(all_prompts, [], [])
        skills_resolved = resolver.resolve_skills(all_skills, [], [])
        hooks_resolved, hook_load_errors = _resolve_hooks(
            artifact_source, resolver, tolerate=tolerate_load_errors
        )

        adapters = discover_adapters(config, rule_registry=rule_registry)

        return cls(
            repo_root=repo_root,
            config=config,
            facts=facts,
            artifact_source=artifact_source,
            state_source=FileSystemStateSource(repo_root=repo_root),
            adapters=adapters,
            rules_resolved=rules_resolved,
            prompts_resolved=prompts_resolved,
            skills_resolved=skills_resolved,
            overlay_collisions=resolver.collisions,
            hooks_resolved=hooks_resolved,
            hook_definitions=resolver.hook_definitions,
            hook_load_errors=hook_load_errors,
            rule_definitions=all_rules,
            rule_load_errors=rule_load_errors,
            hook_violations=resolver.hook_violations,
            policy_tables=PolicyTables() if policy_tables is None else policy_tables,
        )


def _resolve_hooks(
    source: ArtifactSource, resolver: OverlayResolver, *, tolerate: bool
) -> tuple[list[Hook], list[HookSchemaError]]:
    """Merge ``source``'s hooks layer by layer; return them and the load errors.

    Unlike the other kinds, hooks need real layers, because the additive merge
    treats an overlay and a repo-local override differently (§A.6). A malformed
    hook raises unless ``tolerate`` records it (P8c).
    """
    hooks, errors = source.collect_hooks() if tolerate else (source.list_hooks(), [])
    layers = split_hook_layers(hooks, engine_package=engine_package_of(source))
    return resolver.resolve_hooks(*layers), errors
