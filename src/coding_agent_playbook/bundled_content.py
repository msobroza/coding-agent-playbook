"""Where the engine's own content lives (stdlib-only leaf; imports nothing from the engine).

The engine's rules, prompts, eval tasks and bundled plugins sit in one content
root with two homes:

- installed wheel: ``<package>/_content`` (hatch force-includes ``content/``);
- source checkout: ``<repo>/content`` (an editable install finds it next to ``src/``).

This module is the only code that knows those homes. ``config.py`` and
``config_schema.py`` import it, which is why it must stay a leaf.

It also owns the bundled-plugin naming: ``coding_agent_playbook.plugins.<leaf>``
is canonical and ``coding_agent_playbook.packs.<leaf>`` is a deprecated alias.
Plugin leaves resolve only by exact membership in :func:`bundled_plugins`, so
config text is never joined onto a filesystem path unchecked.

Nothing here caches: a plugin directory added by ``git pull`` in an editable
install is visible on the next call.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

ENGINE_PACKAGE = "coding_agent_playbook"
PLUGIN_NAMESPACE = "coding_agent_playbook.plugins"
DEPRECATED_PACK_NAMESPACE = "coding_agent_playbook.packs"
PACKAGED_CONTENT_DIRNAME = "_content"  # inside the installed package
CHECKOUT_CONTENT_DIRNAME = "content"  # at the repository root

# The one module-level seam end-to-end tests may monkeypatch. Functions read it
# at call time (never as a default argument value), so a patch takes effect.
_PACKAGE_DIR: Path = Path(__file__).resolve().parent

_CORE_DIRNAME = "core"
_PLUGINS_DIRNAME = "plugins"
_CHECKOUT_PACKAGE_PARENT = "src"
# Prefixes include the dot, so the bare namespaces never count as a plugin name.
_PLUGIN_PREFIX = PLUGIN_NAMESPACE + "."
_DEPRECATED_PREFIX = DEPRECATED_PACK_NAMESPACE + "."


class BundledContentMissingError(RuntimeError):
    """The engine's content root was found in neither home.

    ``tried`` holds every candidate root, in lookup order, so the CLI can name
    them in its error line.

    Example::

        >>> err = BundledContentMissingError((Path("/a/_content"), Path("/content")))
        >>> err.tried
        (PosixPath('/a/_content'), PosixPath('/content'))
    """

    def __init__(self, tried: tuple[Path, ...]) -> None:
        self.tried = tried
        looked_in = ", ".join(str(path) for path in tried)
        super().__init__(f"bundled content not found (looked in {looked_in})")


def bundled_content_root(package_dir: Path | None = None) -> Path:
    """Return the content root: the wheel's ``_content`` first, then the checkout's ``content``.

    ``package_dir`` defaults to ``_PACKAGE_DIR``. Each candidate must hold a
    ``core/`` directory: a wheel whose force-include was mis-scoped would
    otherwise load zero engine artifacts silently. The checkout candidate counts
    only when the package sits directly under ``src/``.

    Raises :class:`BundledContentMissingError` naming both candidates.

    Example::

        >>> bundled_content_root(Path("/repo/src/coding_agent_playbook"))  # doctest: +SKIP
        PosixPath('/repo/content')
    """
    package = _PACKAGE_DIR if package_dir is None else package_dir
    packaged = package / PACKAGED_CONTENT_DIRNAME
    checkout = package.parent.parent / CHECKOUT_CONTENT_DIRNAME
    if (packaged / _CORE_DIRNAME).is_dir():
        return packaged
    if package.parent.name == _CHECKOUT_PACKAGE_PARENT and (checkout / _CORE_DIRNAME).is_dir():
        return checkout
    raise BundledContentMissingError((packaged, checkout))


def bundled_plugins(content_root: Path | None = None) -> list[str]:
    """Sorted dotted names of the bundled plugins under ``<root>/plugins``.

    A directory counts when its name is an identifier not starting with ``.``
    or ``_`` (so ``__pycache__`` never does). Names keep the on-disk spelling
    from ``iterdir()``, so comparisons stay exact on case-insensitive volumes.

    Example::

        >>> bundled_plugins()  # doctest: +SKIP
        ['coding_agent_playbook.plugins.python_design', 'coding_agent_playbook.plugins.superpowers']
    """
    root = bundled_content_root() if content_root is None else content_root
    plugins_dir = root / _PLUGINS_DIRNAME
    if not plugins_dir.is_dir():
        return []
    return sorted(
        _PLUGIN_PREFIX + entry.name for entry in plugins_dir.iterdir() if _is_plugin_dir(entry)
    )


def _is_plugin_dir(entry: Path) -> bool:
    """True for a directory whose name is a public identifier."""
    name = entry.name
    return entry.is_dir() and name.isidentifier() and not name.startswith((".", "_"))


def canonical_overlay_name(name: str) -> str:
    """Rewrite ``coding_agent_playbook.packs.<rest>`` to the ``plugins`` namespace.

    Only a non-empty ``<rest>`` is rewritten; the bare namespace and every other
    name come back unchanged.

    Example::

        >>> canonical_overlay_name("coding_agent_playbook.packs.superpowers")
        'coding_agent_playbook.plugins.superpowers'
        >>> canonical_overlay_name("acme.rules")
        'acme.rules'
    """
    if not name.startswith(_DEPRECATED_PREFIX) or name == _DEPRECATED_PREFIX:
        return name
    return _PLUGIN_PREFIX + name.removeprefix(_DEPRECATED_PREFIX)


def canonical_overlay_list(names: Iterable[str]) -> tuple[list[str], tuple[str, ...]]:
    """Canonicalize ``names`` in order, and report the deprecated names rewritten.

    There is no dedup: listing an overlay twice is walked twice (the later walk
    wins) before and after canonicalization alike, and the caller's deprecation
    warning tells the user to fix the list.

    Example::

        >>> canonical_overlay_list(["a", "coding_agent_playbook.packs.x"])
        (['a', 'coding_agent_playbook.plugins.x'], ('coding_agent_playbook.packs.x',))
    """
    originals = list(names)
    canonical = [canonical_overlay_name(name) for name in originals]
    rewritten = tuple(old for old, new in zip(originals, canonical, strict=True) if old != new)
    return canonical, rewritten


def is_plugin_namespace(name: str) -> bool:
    """True only for the bare plugin namespace or its deprecated ``packs`` spelling.

    Example::

        >>> is_plugin_namespace("coding_agent_playbook.packs")
        True
        >>> is_plugin_namespace("coding_agent_playbook.plugins.superpowers")
        False
    """
    return name in (PLUGIN_NAMESPACE, DEPRECATED_PACK_NAMESPACE)


def is_bundled_layer(name: str) -> bool:
    """True for the engine and for any name under either plugin namespace.

    Membership is not checked here: ``coding_agent_playbook.plugins.typo`` is
    a bundled layer that :func:`bundled_layer_root` then resolves to ``None``.

    Example::

        >>> is_bundled_layer("coding_agent_playbook.packs.superpowers")
        True
        >>> is_bundled_layer("coding_agent_playbook.plugins")
        False
    """
    return name == ENGINE_PACKAGE or name.startswith((_PLUGIN_PREFIX, _DEPRECATED_PREFIX))


def bundled_layer_root(name: str, *, content_root: Path | None = None) -> Path | None:
    """Return the directory holding a bundled layer's kind directories, or ``None``.

    The engine maps to ``<root>/core``. A plugin name (either namespace) maps to
    ``<root>/plugins/<leaf>`` only when its canonical form is exactly an entry
    of :func:`bundled_plugins`; an empty leaf, ``..``, ``/``, nested dots, the
    wrong case or ``__pycache__`` give ``None``, as does any non-bundled name.

    Raises :class:`BundledContentMissingError` when ``content_root`` is omitted
    and no content root is found.

    Example::

        >>> bundled_layer_root("coding_agent_playbook.packs.superpowers")  # doctest: +SKIP
        PosixPath('/repo/content/plugins/superpowers')
    """
    if not is_bundled_layer(name):
        return None
    root = bundled_content_root() if content_root is None else content_root
    if name == ENGINE_PACKAGE:
        return root / _CORE_DIRNAME
    return _plugin_dir(root, canonical_overlay_name(name))


def _plugin_dir(root: Path, canonical: str) -> Path | None:
    """``<root>/plugins/<leaf>`` when ``canonical`` is a listed plugin, else ``None``."""
    # Membership first: the leaf below is joined only after an exact match
    # against on-disk names, never straight from config text.
    if canonical not in bundled_plugins(root):
        return None
    return root / _PLUGINS_DIRNAME / canonical.removeprefix(_PLUGIN_PREFIX)
