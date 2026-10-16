"""The ``sentinel`` and ``protected`` tables of ``guard_config.json`` (specs/prK-hook-pack.md §E.0.5, §E.1).

guard-generated-outputs (and, in later K5 steps, control-plane-guard and the
``drift`` Stop stage) decide what is generated from data rendered here at sync,
so the hot path never renders a template or spawns ``playbook``:

- ``entries``: the sync's written set as lock rows ``{path, kind, artifact_id,
  source, scope}``, exactly what the lockfile records (P4 provenance), plus
  ``sha256`` on the scoped rows (the managed ``settings.json`` elements), so
  control-plane-guard can tell a managed element from a user one;
- ``output_dirs``: each enabled adapter's sentinel-scanned ``_output_directories()``
  (repo-relative, trailing ``/``) plus its composite singletons, the files a
  sentinel can mark as engine output;
- ``hook_artifacts``: the guardrail files themselves, which only the user may change;
- ``resource_roots``: package-relative ids (``pkg:<package>/resources``) of the
  engine and every ``overlays_enabled`` layer (bundled plugins included); the
  runtime resolves them through ``machine.json``, never through an absolute path
  here. The id keeps that spelling for every layer, so the rendered table did
  not change when the engine's content left the package: an overlay package's
  id names its ``resources/``, a bundled layer's names its directory in the
  catalog (``catalog/core/``, ``catalog/plugins/<leaf>/``).

Everything is machine-independent (§D.8.3): ``sync --check`` byte-compares it.
Split out of ``guard_config`` for the module-size budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

# The stdlib-only paths module, not the adapter: this sync-time module stays free
# of the renderer (jinja2, yaml), and no adapter import can cycle back here.
from coding_agent_playbook.adapters.claude_rule_paths import CLAUDE_CODE_COMPOSITES

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.lockfile import LockEntry, Provenance

__all__ = [
    "COMPOSITE_SINGLETONS",
    "ProtectInputs",
    "ProtectedRow",
    "adapter_output_dirs",
    "protected_rows",
    "protected_table",
    "resolve_resource_roots",
    "resource_root_ids",
]

#: The multi-source files each adapter's ``finalize`` writes, by adapter name.
#: ``claude_code`` composes two since its rules (and hook advisories and the
#: heartbeat line) moved to ``.claude/rules/coding-agent-playbook.md`` beside a
#: rule-free ``.claude/CLAUDE.md`` stub (SPEC §10.3.1): guard-generated-outputs
#: must deny an edit of either, and the drift scan must see either as an orphan.
COMPOSITE_SINGLETONS: Final[Mapping[str, tuple[str, ...]]] = {
    "claude_code": CLAUDE_CODE_COMPOSITES,
    "agents_md": ("AGENTS.md",),
}
_RESOURCE_ID: Final = "pkg:{package}/resources"


@dataclass(frozen=True)
class ProtectedRow:
    """One ``protected.entries`` row: a lock entry's path and provenance (no content hash).

    ``sha256`` is kept only for a scoped row (one managed JSON element).

    Example::

        >>> ProtectedRow("AGENTS.md", "composite").to_json()["kind"]
        'composite'
    """

    path: str
    kind: str
    artifact_id: str = ""
    source: str = ""
    scope: str = ""
    sha256: str = ""

    def to_json(self) -> dict[str, str]:
        """The row as rendered: ``sha256`` only when ``scope`` is set."""
        row = {
            "path": self.path,
            "kind": self.kind,
            "artifact_id": self.artifact_id,
            "source": self.source,
            "scope": self.scope,
        }
        if self.scope:
            row["sha256"] = self.sha256
        return row


@dataclass(frozen=True)
class ProtectInputs:
    """What the ``protected`` table is rendered from; all of it machine-independent.

    Example::

        ProtectInputs(entries=protected_rows(prov, managed, root),
                      output_dirs=adapter_output_dirs(adapters, root),
                      packages=("coding_agent_playbook",))
    """

    entries: Sequence[ProtectedRow] = ()
    output_dirs: Sequence[str] = ()
    packages: Sequence[str] = ()


def protected_rows(
    provenance: Mapping[Path, Provenance],
    managed: Sequence[LockEntry],
    out_root: Path,
    *,
    shared: Collection[str] = (),
) -> list[ProtectedRow]:
    """The rows the lockfile will hold for this sync's writes, in lockfile order.

    Mirrors ``commands._sync_lockfile.build_lockfile``: one whole-file row per
    written path (``provenance`` is keyed by resolved path) except the paths
    owned element-wise by ``managed`` or co-owned (``shared``), then the scoped
    rows. Paths are POSIX and relative to ``out_root`` (the repo, or the
    ``--check`` scratch dir), so both modes render the same bytes.

    Example::

        rows = protected_rows(recorder.provenance, recorder.managed, out_root,
                              shared=(".claude/settings.json",))
    """
    root = out_root.resolve()
    skipped = {entry.path for entry in managed} | set(shared)
    rows = [
        ProtectedRow(rel, origin.kind, origin.artifact_id, origin.source)
        for path, origin in sorted(provenance.items())
        if (rel := _relative(path, root)) is not None and rel not in skipped
    ]
    rows.extend(
        ProtectedRow(e.path, e.kind, e.artifact_id, e.source, e.scope, e.sha256) for e in managed
    )
    return rows


def adapter_output_dirs(adapters: Mapping[str, Adapter], out_root: Path) -> list[str]:
    """Each adapter's sentinel-scan dirs (``x/``) and composite singletons, repo-relative, sorted.

    The same directories the adapters' ``stale_outputs`` scan, so a guard and
    ``sync --check`` agree on which sentinel files are engine output; native
    skill dirs are lockfile-only (main #25) and never listed.

    Example::

        >>> adapter_output_dirs({"continue": ContinueAdapter()}, Path("/r"))  # doctest: +SKIP
        ['.continue/prompts/', '.continue/rules/']
    """
    root = out_root.resolve()
    found: set[str] = set()
    for name, adapter in adapters.items():
        for directory in adapter._output_directories(out_root):
            rel = _relative(directory.resolve(), root)
            if rel is not None and rel != ".":
                found.add(f"{rel}/")
        found.update(COMPOSITE_SINGLETONS.get(name, ()))
    return sorted(found)


def resource_root_ids(packages: Iterable[str]) -> list[str]:
    """``pkg:<package>/resources`` for each layer package, in layer order, deduplicated.

    Example::

        >>> resource_root_ids(["coding_agent_playbook"])
        ['pkg:coding_agent_playbook/resources']
    """
    return list(dict.fromkeys(_RESOURCE_ID.format(package=p) for p in packages))


def resolve_resource_roots(packages: Iterable[str]) -> dict[str, str]:
    """``machine.json``'s ``resource_roots``: each id's absolute layer dir on this machine.

    An overlay package resolves to its ``resources/`` through
    ``importlib.resources``; one that cannot be imported, or ships no
    ``resources/``, is left out (the preflight already refused such an
    overlay). A bundled layer (the engine, a bundled plugin) resolves to its
    directory in the catalog and is never imported; an unknown plugin
    leaf is left out the same way. Sync-time only.

    Example::

        >>> resolve_resource_roots(["coding_agent_playbook"])  # doctest: +SKIP
        {'pkg:coding_agent_playbook/resources': '/v/site-packages/coding_agent_playbook/_catalog/core'}
    """
    found: dict[str, str] = {}
    for package in dict.fromkeys(packages):
        root = _layer_dir(package)
        if root is not None:
            found[_RESOURCE_ID.format(package=package)] = root
    return found


def _layer_dir(package: str) -> str | None:
    """The directory holding ``package``'s kind dirs, or ``None`` when it has none."""
    from importlib import resources

    from coding_agent_playbook.catalog import catalog_layer_root, is_bundled_layer

    if is_bundled_layer(package):
        bundled = catalog_layer_root(package)
        return str(bundled) if bundled is not None and bundled.is_dir() else None
    try:
        root = resources.files(package).joinpath("resources")
    except Exception:  # an overlay's import may raise anything; it is skipped
        return None
    return str(root) if root.is_dir() else None


def protected_table(inputs: ProtectInputs, hook_artifacts: Sequence[str]) -> dict[str, Any]:
    """The ``protected`` table: sorted rows, output dirs, hook artifacts, resource ids.

    Example::

        >>> protected_table(ProtectInputs(), ())["entries"]
        []
    """
    rows = sorted(inputs.entries, key=lambda row: (row.path, row.scope))
    return {
        "entries": [row.to_json() for row in rows],
        "output_dirs": sorted(set(inputs.output_dirs)),
        "hook_artifacts": list(hook_artifacts),
        "resource_roots": resource_root_ids(inputs.packages),
    }


def _relative(path: Path, root: Path) -> str | None:
    """``path`` relative to ``root`` as POSIX, or ``None`` outside it."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None
