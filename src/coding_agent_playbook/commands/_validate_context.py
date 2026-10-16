"""The context ``playbook validate`` builds without a consumer config (prK §P P8a).

An engine or overlay checkout has no ``.coding-agent-playbook.toml``, so
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

from importlib import resources
from pathlib import Path
from typing import Final

from coding_agent_playbook import __version__
from coding_agent_playbook.config import Config, ProjectMeta
from coding_agent_playbook.orchestrator import SyncContext
from coding_agent_playbook.sources.filesystem import (
    ENGINE_PACKAGE,
    FileSystemArtifactSource,
    FileSystemStateSource,
)

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
    return (repo_root / FileSystemStateSource._CONFIG_FILENAME).is_file()


def config_less_notes(repo_root: Path) -> list[str]:
    """The lines validate prints before its result when there is no consumer config.

    Example::

        >>> config_less_notes(Path("/repo"))[1]
        'skipped: overlays_enabled usability (no overlay list to check)'
    """
    return [
        f"note: no {FileSystemStateSource._CONFIG_FILENAME} in {repo_root}; validating the "
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
        # Like sources.filesystem._resource_subdir: an import may raise anything.
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
        repo_root, _config_less_config(repo_root), artifact_source=source, tolerate_hook_errors=True
    )


def _config_less_config(repo_root: Path) -> Config:
    """A consumer config as ``playbook init`` would start one, with nothing enabled."""
    return Config(
        schema_version=1,
        project=ProjectMeta(name=repo_root.resolve().name, kind=_CONFIG_LESS_KIND),
        engine_version=__version__,
    )
