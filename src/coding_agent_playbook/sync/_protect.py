"""The ``protected`` table's sync-side inputs: this sync's lock rows and the adapters' scan dirs.

``guard_config.json``'s ``protected`` table (``hooks.guard_config._tables_protect``)
lets guard-generated-outputs and control-plane-guard decide what is generated
without rendering a template or spawning ``playbook``. Its rows need what only
sync has: the written set as lock rows ``{path, kind, artifact_id, source,
scope}``, exactly what the lockfile records (P4 provenance), plus ``sha256`` on
the scoped rows (the managed ``settings.json`` elements); and each enabled
adapter's sentinel-scanned ``_output_directories()`` (repo-relative, trailing
``/``) plus its composite singletons. Both need the adapters, and the guard_config
writer sits below them, so they are assembled here and handed over as
``ProtectInputs`` (GC-D1).

Everything is machine-independent (§D.8.3): ``sync --check`` byte-compares it.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

# The stdlib-only paths module, not the adapter: this sync-time module stays free
# of the renderer (jinja2, yaml), and no adapter import can cycle back here.
from coding_agent_playbook.adapters.claude_code.paths import CLAUDE_CODE_COMPOSITES
from coding_agent_playbook.generated_output.symlinks import real_path
from coding_agent_playbook.hooks.guard_config.inputs import ProtectedRow
from coding_agent_playbook.lockfile.model import merge_provenance

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.lockfile.model import LockEntry, Provenance

__all__ = ["COMPOSITE_SINGLETONS", "adapter_output_dirs", "protected_rows"]

#: The multi-source files each adapter's ``finalize`` writes, by adapter name.
#: ``claude_code`` composes two since its rules (and hook advisories and the
#: heartbeat line) moved to ``.claude/rules/coding-agent-playbook.md`` beside a
#: rule-free ``.claude/CLAUDE.md`` stub (SPEC §10.3.1): guard-generated-outputs
#: must deny an edit of either, and the drift scan must see either as an orphan.
COMPOSITE_SINGLETONS: Final[Mapping[str, tuple[str, ...]]] = {
    "claude_code": CLAUDE_CODE_COMPOSITES,
    "agents_md": ("AGENTS.md",),
}


def protected_rows(
    provenance: Mapping[Path, Provenance],
    managed: Sequence[LockEntry],
    out_root: Path,
    *,
    shared: Collection[str] = (),
    repo_root: Path | None = None,
) -> list[ProtectedRow]:
    """The rows the lockfile will hold for this sync's writes, in lockfile order.

    Mirrors ``sync._dispatch.build_lockfile``: one whole-file row per
    written path (``provenance`` is keyed by resolved path) except the paths
    owned element-wise by ``managed`` or co-owned (``shared``), then the scoped
    rows. Paths are POSIX and relative to the real repo (``repo_root``, which
    defaults to ``out_root``): a ``--check`` scratch path is mapped onto the repo
    first (:func:`_lock_path_via_repo_links`), and paths that land on one repo
    file merge like the lockfile's (``merge_provenance``: two adapters' skills
    roots linked to one directory give one ``composite`` row), in the lockfile's
    path order, so both modes render the same bytes.

    Example::

        rows = protected_rows(recorder.provenance, recorder.managed, out_root,
                              shared=(".claude/settings.json",), repo_root=repo)
    """
    repo = out_root if repo_root is None else repo_root
    skipped = {entry.path for entry in managed} | set(shared)
    merged: dict[str, Provenance] = {}
    for path, origin in provenance.items():
        rel = _lock_path_via_repo_links(path, out_root, repo)
        if rel is not None and rel not in skipped:
            merged[rel] = merge_provenance(merged.get(rel), origin)
    # PurePosixPath order, not string order: the lockfile sorts resolved Paths.
    ordered = sorted(merged.items(), key=lambda item: PurePosixPath(item[0]))
    rows = [ProtectedRow(rel, o.kind, o.artifact_id, o.source) for rel, o in ordered]
    rows.extend(
        ProtectedRow(e.path, e.kind, e.artifact_id, e.source, e.scope, e.sha256) for e in managed
    )
    return rows


def adapter_output_dirs(
    adapters: Mapping[str, Adapter], out_root: Path, *, repo_root: Path | None = None
) -> list[str]:
    """Each adapter's sentinel-scan dirs (``x/``) and composite singletons, repo-relative, sorted.

    The same directories the adapters' ``stale_outputs`` scan, so a guard and
    ``sync --check`` agree on which sentinel files are engine output; native
    skill dirs are lockfile-only (main #25) and never listed. Each directory is
    mapped onto ``repo_root`` (default ``out_root``) like :func:`protected_rows`,
    so a symlinked ``.claude/commands`` lists its target in both modes.

    Example::

        >>> adapter_output_dirs({"continue": ContinueAdapter()}, Path("/r"))  # doctest: +SKIP
        ['.continue/prompts/', '.continue/rules/']
    """
    repo = out_root if repo_root is None else repo_root
    found: set[str] = set()
    for name, adapter in adapters.items():
        for directory in adapter._output_directories(out_root):
            rel = _lock_path_via_repo_links(directory, out_root, repo)
            if rel is not None and rel != ".":
                found.add(f"{rel}/")
        found.update(COMPOSITE_SINGLETONS.get(name, ()))
    return sorted(found)


def _lock_path_via_repo_links(path: Path, out_root: Path, repo_root: Path) -> str | None:
    """``path`` (rendered under ``out_root``) as the repo-relative POSIX path write mode records.

    The path is mapped onto ``repo_root`` and resolved through the repo's own
    symlinks, like ``sync._on_real_tree`` followed by ``build_lockfile``'s
    resolve. Without that a symlinked skills root (``.claude/skills ->
    ../.agents/skills``) gave ``.agents/skills/…`` rows in write mode but
    ``.claude/skills/…`` in the ``--check`` scratch, a drift no sync clears.
    ``None`` when the path lies outside ``out_root`` or resolves out of the repo
    (the lockfile gives such a path no entry, and the protected table drops it
    in both modes).

    Example::

        _lock_path_via_repo_links(scratch / ".claude/skills/x/SKILL.md", scratch, repo)
        # -> ".agents/skills/x/SKILL.md" when the repo links .claude/skills there
    """
    # real_path, not Path.resolve(): Python 3.12's raises on a link loop in the repo.
    inside = _relative(real_path(path), real_path(out_root))
    if inside is None:
        return None
    return _relative(real_path(repo_root / inside), real_path(repo_root))


def _relative(path: Path, root: Path) -> str | None:
    """``path`` relative to ``root`` as POSIX, or ``None`` outside it."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None
