"""Environment checks run before ``playbook sync`` renders (SPEC §12.2, §13.1).

A sync that cannot use every configured overlay package silently renders
*without* it: ``FileSystemArtifactSource`` treats a package that fails to import
(missing, or raising at import time) — or an importable one with no
``resources/`` directory — like one that ships no artifacts. That is exactly what happens when the remote ``language: python``
pre-commit hooks run in pre-commit's isolated venv, which holds only the engine
at ``rev:`` — the post-checkout auto-sync would delete the org rules and shrink
the managed ``.gitignore`` block on every checkout. So an unusable overlay is a
hard error (non-zero exit, package and reason named, nothing written). A missing
*adapter* is only warned about: its old output is kept and stays ignored (see
``_sync_orphans``), so nothing is lost or published.

:func:`unusable_overlays` is the one overlay check every command shares:
``sync`` refuses, ``validate`` fails, ``check`` flags, ``init --overlays`` refuses.
"""

from __future__ import annotations

import difflib
import importlib
import pkgutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook import packs as _packs
from coding_agent_playbook.bundled_content import bundled_layer_root, is_bundled_layer

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from types import ModuleType

_HOOK_VENV_HINT = (
    "A pre-commit hook from the engine's .pre-commit-hooks.yaml (language: python) runs in\n"
    "pre-commit's own venv: list the package under that hook's additional_dependencies, or\n"
    "use the repo: local + language: system hooks that 'playbook init' writes."
)

_NOT_IMPORTABLE = "not importable"
_NO_RESOURCES = "importable, but ships no resources/ directory, so it is not an overlay package"
_NO_SUCH_PLUGIN = "no such bundled plugin"

#: The engine's top-level package; a name starting with it reads like a pack typo.
_ENGINE_PACKAGE = _packs.__name__.partition(".")[0]

#: How close a name's last segment must be to a bundled pack's to earn the hint.
_PACK_NAME_SIMILARITY = 0.75


@dataclass(frozen=True)
class UnusableOverlay:
    """A configured overlay package that cannot contribute artifacts here.

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

    An overlay is unusable when importing it fails, or when it imports but ships
    no ``resources/`` directory (e.g. the parent ``coding_agent_playbook.packs``):
    either way rendering would silently drop it. Each overlay is imported, as
    rendering's ``importlib.resources.files`` would, so a package that raises at
    import time is reported here — with its error — instead of crashing later. A
    name that reads like a mistyped bundled pack gets the pack list in its reason.

    Example::

        >>> [str(problem) for problem in unusable_overlays(["coding_agent_playbook", "nope"])]
        ['nope: not importable']
    """
    found: list[UnusableOverlay] = []
    for name in overlays:
        reason = _unusable_reason(name)
        if reason is not None:
            found.append(UnusableOverlay(name, reason + _pack_hint(name)))
    return found


def bundled_packs(parent: ModuleType = _packs) -> list[str]:
    """Dotted names of the packs bundled in the engine wheel, sorted.

    Discovered with :mod:`pkgutil` under ``parent`` (the engine's ``packs``
    package; injectable for tests), so adding a pack needs no list update here.
    Only subpackages count: a helper module there would not be a pack.

    Example::

        >>> "coding_agent_playbook.packs.superpowers" in bundled_packs()
        True
    """
    prefix = f"{parent.__name__}."
    return sorted(info.name for info in pkgutil.iter_modules(parent.__path__, prefix) if info.ispkg)


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
        f"error: overlay package(s) in overlays_enabled are not usable here:\n{listed}"
        "Rendering without them would drop their rules and un-ignore their output, so nothing\n"
        "was written. Fix the name, or install the package where 'playbook' runs.\n"
        f"{_HOOK_VENV_HINT}",
        file=sys.stderr,
    )


def warn_missing_adapters(names: Sequence[str]) -> None:
    """Warn on stderr that enabled adapters were skipped (their old output is kept)."""
    print(
        f"warning: enabled adapter(s) not installed, skipped: {', '.join(names)}.\n"
        "Their previously generated output is kept (and stays gitignored) until they are\n"
        f"installed or removed from adapters_enabled.\n{_HOOK_VENV_HINT}",
        file=sys.stderr,
    )


def _unusable_reason(name: str) -> str | None:
    """Why ``name`` cannot serve as an overlay, or ``None`` when it can.

    A bundled layer is checked against the content tree and never imported: the
    engine always resolves, and a plugin name (either namespace) resolves only
    when its leaf is a directory under ``content/plugins/``. Every other name is
    imported and must ship a ``resources/`` directory.
    """
    if is_bundled_layer(name):
        return None if bundled_layer_root(name) is not None else _NO_SUCH_PLUGIN
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

    Mirrors ``sources.filesystem._resource_subdir``: a plain module (no
    ``__path__``) or a package without that directory contributes nothing.
    """
    locations: Iterable[str] = getattr(module, "__path__", None) or []
    return any((Path(location) / "resources").is_dir() for location in locations)


def _pack_hint(name: str) -> str:
    """`` (bundled packs: …)`` when ``name`` reads like a mistyped bundled pack, else ``""``."""
    available = bundled_packs()
    if not available or not _looks_like_pack(name, available):
        return ""
    return f" (bundled packs: {', '.join(available)})"


def _looks_like_pack(name: str, available: Sequence[str]) -> bool:
    """True for a name under the engine package, or whose last segment is near a pack's.

    Hyphens count as underscores, so a distribution-style spelling still matches.
    """
    normalized = name.replace("-", "_")
    if normalized.partition(".")[0] == _ENGINE_PACKAGE:
        return True
    leaves = [pack.rpartition(".")[2] for pack in available]
    leaf = normalized.rpartition(".")[2]
    return bool(difflib.get_close_matches(leaf, leaves, n=1, cutoff=_PACK_NAME_SIMILARITY))
