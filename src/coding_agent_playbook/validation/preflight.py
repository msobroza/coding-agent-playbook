"""Environment checks run before ``playbook sync`` renders (SPEC §12.2, §13.1).

Every ``overlays_enabled`` entry is an overlay package or bundled plugin, and a
sync that cannot use one silently renders *without* it:
``FileSystemArtifactSource`` treats an overlay package that fails to import
(missing, or raising at import time) — or an importable one with no
``resources/`` directory — and a bundled-plugin name with no
``catalog/plugins/<leaf>/`` directory like a layer that ships no artifacts. The
import failure is exactly what happens when the remote ``language: python``
pre-commit hooks run in pre-commit's isolated venv, which holds only the engine
at ``rev:`` — the post-checkout auto-sync would delete the org rules and shrink
the managed ``.gitignore`` block on every checkout. So an unusable overlay
package or bundled plugin is a hard error (non-zero exit, name and reason given,
nothing written). A missing *adapter* is only warned about: its old output is
kept and stays ignored (see ``_sync_orphans``), so nothing is lost or published.

:func:`unusable_overlays` is the one overlay check every command shares:
``sync`` refuses, ``validate`` fails, ``check`` flags, ``init --overlays`` refuses.
"""

from __future__ import annotations

import difflib
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.roots import (
    ENGINE_PACKAGE,
    catalog_layer_root,
    is_bundled_layer,
    is_plugin_namespace,
)

# Re-exported: the preflight's callers and tests list the bundled plugins from here.
from coding_agent_playbook.catalog.roots import bundled_plugins as bundled_plugins

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from types import ModuleType

_HOOK_VENV_HINT = (
    "A pre-commit hook from the engine's .pre-commit-hooks.yaml (language: python) runs in\n"
    "pre-commit's own venv: list the package under that hook's additional_dependencies, or\n"
    "use the repo: local + language: system hooks that 'playbook init' writes."
)

_NOT_IMPORTABLE = "not importable"
_NO_RESOURCES = "importable, but ships no resources/ directory, so it is not an overlay package"
_NO_SUCH_PLUGIN = "no such bundled plugin"
_PLUGIN_NAMESPACE_REASON = "the bundled plugin namespace, not a plugin"

#: How close a name's last segment must be to a bundled plugin's to earn the hint.
_PLUGIN_NAME_SIMILARITY = 0.75

#: Names that are a harness, not an adapter, with where that harness's output comes
#: from. ``playbook init`` offered ``codex`` before SPEC v0.21; listed, it makes every
#: sync keep all leftovers (``keep_all``), so the warning names the fix.
_NOT_ADAPTERS: Final[Mapping[str, str]] = MappingProxyType(
    {"codex": "Codex reads AGENTS.md and .agents/skills/ (the shared_skills adapter)"}
)


@dataclass(frozen=True)
class UnusableOverlay:
    """A configured overlay package or bundled plugin that cannot contribute artifacts here.

    Example::

        >>> str(UnusableOverlay("org_overlay", "not importable"))
        'org_overlay: not importable'
    """

    name: str
    reason: str

    def __str__(self) -> str:
        return f"{self.name}: {self.reason}"


def unusable_overlays(overlays: Sequence[str]) -> list[UnusableOverlay]:
    """Return, in order, the configured overlays that cannot contribute artifacts here.

    Each entry is an overlay package or bundled plugin. An overlay package is
    unusable when importing it fails, or when it imports but ships no
    ``resources/`` directory (e.g. ``json``): either way rendering would
    silently drop it. It is imported, as rendering's ``importlib.resources.files``
    would, so a package that raises at import time is reported here — with its
    error — instead of crashing later. A bundled-plugin name is never imported:
    it is unusable when no ``catalog/plugins/<leaf>/`` matches it, and the bare
    plugin namespace is never a plugin. A name that reads like a mistyped bundled
    plugin gets the plugin list in its reason.

    Example::

        >>> [str(problem) for problem in unusable_overlays(["coding_agent_playbook", "nope"])]
        ['nope: not importable']
    """
    found: list[UnusableOverlay] = []
    for name in overlays:
        reason = _unusable_reason(name)
        if reason is not None:
            found.append(UnusableOverlay(name, reason + _plugin_hint(name)))
    return found


def missing_adapters(enabled: Iterable[str], discovered: Iterable[str]) -> list[str]:
    """Return the enabled adapter names no installed entry point provides.

    Example::

        >>> missing_adapters(["continue", "codex"], ["continue", "agents_md"])
        ['codex']
    """
    return sorted(set(enabled) - set(discovered))


def report_unusable_overlays(problems: Sequence[UnusableOverlay]) -> None:
    """Explain on stderr why the sync refused to run, one overlay per line."""
    listed = "".join(f"  {problem}\n" for problem in problems)
    print(
        "error: overlay package(s) or bundled plugin(s) in overlays_enabled are not usable "
        f"here:\n{listed}"
        "Rendering without them would drop their rules and un-ignore their output, so nothing\n"
        "was written. Fix the name, or install the overlay package where 'playbook' runs.\n"
        f"{_HOOK_VENV_HINT}",
        file=sys.stderr,
    )


def warn_missing_adapters(names: Sequence[str]) -> None:
    """Warn on stderr that enabled adapters were skipped (their old output is kept).

    A name no adapter provides by design (``codex``) gets a one-line fix hint.

    Example::

        >>> warn_missing_adapters(["codex"])  # doctest: +SKIP
    """
    print(
        f"warning: enabled adapter(s) not installed, skipped: {', '.join(names)}.\n"
        "Their previously generated output is kept (and stays gitignored) until they are\n"
        f"installed or removed from adapters_enabled.\n{_not_adapter_hints(names)}"
        f"{_HOOK_VENV_HINT}",
        file=sys.stderr,
    )


def _not_adapter_hints(names: Sequence[str]) -> str:
    """One line per name in ``names`` that no adapter provides by design.

    Example::

        >>> _not_adapter_hints(["codex", "custom"]).count("\\n")
        1
    """
    return "".join(
        f"'{name}' is not an adapter: {_NOT_ADAPTERS[name]}; remove it from adapters_enabled.\n"
        for name in names
        if name in _NOT_ADAPTERS
    )


def warn_legacy_cleanup(name: str) -> None:
    """Warn on stderr that ``--check`` skips orphan reporting for adapter ``name``.

    The adapter overrides ``cleanup_stale`` but not ``stale_outputs`` (the
    pre-v0.16 contract, SPEC §10.1), so the check cannot tell what it deletes.

    Example::

        >>> warn_legacy_cleanup("my_adapter")  # doctest: +SKIP
    """
    print(
        f"warning: adapter {name!r} overrides cleanup_stale() but not stale_outputs(); "
        "'playbook sync --check'\ncannot see what its cleanup deletes, so it does not "
        "report that adapter's orphans.\nOverride stale_outputs() instead "
        "(SPEC §10.1, MIGRATION.md).",
        file=sys.stderr,
    )


def _unusable_reason(name: str) -> str | None:
    """Why ``name`` cannot serve as an overlay, or ``None`` when it can.

    The first two checks import nothing. The bare plugin namespace (either
    spelling) is never a plugin, so a leftover ``packs/`` directory holding only
    bytecode caches cannot change the result. A bundled layer is checked against
    the catalog tree: the engine resolves to ``core/``, and a plugin name (either
    namespace) resolves only when its leaf is a directory under
    ``catalog/plugins/``. Every other name is imported and must ship a
    ``resources/`` directory.
    """
    if is_plugin_namespace(name):
        return _PLUGIN_NAMESPACE_REASON
    if is_bundled_layer(name):
        return None if catalog_layer_root(name) is not None else _NO_SUCH_PLUGIN
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        # Whatever the import raises — no such module, an invalid name, the
        # package's own code failing — rendering would skip it, so it is a
        # reason to report, never a crash (``import_module`` imports the parents
        # of a dotted name too, and those may raise anything).
        return _import_failure_reason(name, exc)
    return None if _ships_resources(module) else _NO_RESOURCES


def _import_failure_reason(name: str, exc: Exception) -> str:
    """``not importable``, plus the error unless it only says ``name`` does not exist.

    Example::

        >>> _import_failure_reason("org", ModuleNotFoundError("No module named 'org'", name="org"))
        'not importable'
    """
    if isinstance(exc, ModuleNotFoundError) and _names_itself_or_a_parent(exc.name, name):
        return _NOT_IMPORTABLE
    return f"{_NOT_IMPORTABLE} ({type(exc).__name__}: {exc})"


def _names_itself_or_a_parent(missing: str | None, name: str) -> bool:
    """True when ``missing`` is ``name`` or one of its parent packages.

    Anything else is a dependency the overlay itself failed to import, which
    the reason names so it is not mistaken for a misspelled overlay.
    """
    return missing is not None and (name == missing or name.startswith(f"{missing}."))


def _ships_resources(module: ModuleType) -> bool:
    """True when the package has a ``resources/`` dir, where overlays keep artifacts.

    Mirrors ``catalog.source._resource_subdir``: a plain module (no
    ``__path__``) or a package without that directory contributes nothing.
    """
    locations: Iterable[str] = getattr(module, "__path__", None) or []
    return any((Path(location) / "resources").is_dir() for location in locations)


def _plugin_hint(name: str) -> str:
    """`` (bundled plugins: …)`` when ``name`` reads like a mistyped bundled plugin, else ``""``."""
    available = bundled_plugins()
    if not available or not _looks_like_plugin(name, available):
        return ""
    return f" (bundled plugins: {', '.join(available)})"


def _looks_like_plugin(name: str, available: Sequence[str]) -> bool:
    """True for a name under the engine package, or whose last segment is near a plugin's.

    Hyphens count as underscores, so a distribution-style spelling still matches.
    """
    normalized = name.replace("-", "_")
    if normalized.partition(".")[0] == ENGINE_PACKAGE:
        return True
    leaves = [plugin.rpartition(".")[2] for plugin in available]
    leaf = normalized.rpartition(".")[2]
    return bool(difflib.get_close_matches(leaf, leaves, n=1, cutoff=_PLUGIN_NAME_SIMILARITY))
