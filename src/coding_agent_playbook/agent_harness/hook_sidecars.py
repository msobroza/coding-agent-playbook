"""Hooks in the agent_harness tree, both directions (specs/prK-lifecycle-hooks.md §C.6).

The Agent Harness spec has no lifecycle-event concept, so ``agent_harness`` is
advisory-only. It still keeps the ``playbook/hooks/`` -> harness ->
``import-harness`` round trip lossless: :func:`emit_hook_sidecars` writes the
sidecar, and :func:`read_hook_sidecar` turns its manifest entry back into the
canonical ``Hook`` (its read half joined this module in AH-2, #143):

- **sidecar (always):** ``.playbook/hooks/<id>/HOOK.md`` with the canonical
  frontmatter, the sentinel as first body line and the un-rendered body, plus
  ``scripts/`` byte-copied with their exec bits; recorded as manifest kind
  ``hook``. ``.playbook/`` carries ``.harnessleaf``, so clients treat it as opaque;
- **advisory (non-blank body only):** the hook's advisory rule, which the
  adapter writes as ``rules/30-guardrail-<id>.md`` with no manifest entry, so a
  lossless import never turns it into a spurious ``Rule``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.agent_harness import emitter, manifest
from coding_agent_playbook.agent_harness._import_writes import restore_recorded_exec_bits
from coding_agent_playbook.artifacts.frontmatter import format_frontmatter
from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.generated_output.output_io import write_output_text
from coding_agent_playbook.generated_output.source_files import copyable_skill_files
from coding_agent_playbook.rendering.formats import with_sentinel_body

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = [
    "HOOKS_SIDECAR",
    "copy_scripts",
    "emit_hook_sidecars",
    "guardrail_rules",
    "read_hook_sidecar",
    "stale_sidecar_candidates",
]

#: Repo-relative POSIX home of the hook sidecars, inside the opaque ``.playbook/``.
HOOKS_SIDECAR: Final = f"{manifest.SIDECAR_DIRNAME}/hooks"
_MARKER: Final = "HOOK.md"


def emit_hook_sidecars(
    hooks: Sequence[ResolvedHook], repo_root: Path, entries: list[manifest.ManifestEntry]
) -> list[Path]:
    """Write every hook's sidecar (sorted by id) and append its manifest entry; return the paths.

    A hook without a ``definition`` (built in memory, never resolved from a
    source) has no canonical form to copy and is skipped.

    Example::

        written = emit_hook_sidecars(self._hooks, repo_root, entries)
    """
    written: list[Path] = []
    for hook in sorted(hooks, key=lambda h: h.id):
        if hook.definition is not None:
            written.extend(_emit_sidecar(hook.definition, repo_root, entries))
    return written


def _emit_sidecar(hook: Hook, repo_root: Path, entries: list[manifest.ManifestEntry]) -> list[Path]:
    hook_dir = repo_root / HOOKS_SIDECAR / hook.frontmatter.id
    hook_dir.mkdir(parents=True, exist_ok=True)
    mapping = hook.frontmatter.to_mapping()
    target = hook_dir / _MARKER
    head = format_frontmatter(mapping, "")
    write_output_text(target, with_sentinel_body(head, hook.template_body))
    scripts, copied = copy_scripts(hook.scripts_dir, hook_dir / "scripts", repo_root)
    entries.append(
        manifest.ManifestEntry(
            kind="hook",
            path=target.relative_to(repo_root).as_posix(),
            id=hook.frontmatter.id,
            name=hook.frontmatter.name,
            body=hook.template_body,
            is_templated=hook.is_templated,
            hook_frontmatter=mapping,
            scripts=scripts,
        )
    )
    return [target, *copied]


def read_hook_sidecar(path: Path, entry: manifest.ManifestEntry, *, source_package: str) -> Hook:
    """Rebuild the ``Hook`` that ``entry`` records; ``path`` is its sidecar ``HOOK.md``.

    The frontmatter, the un-rendered body and ``is_templated`` come from the
    manifest entry, never from the rendered advisory, and the scripts whose
    exec bit the entry records get it back (a transport may have dropped it).
    Raises ``HookSchemaError`` (naming the field and value) when the recorded
    frontmatter no longer parses; the importer reports it and skips the entry.

    ``source_package`` is required, unlike the spec's two-argument signature
    (prT AC.4.4): the marker is ``importer.IMPORTED_SOURCE_PACKAGE``, and this
    module cannot import it, since ``importer`` -> ``_lossless`` -> here is a cycle.

    Example::

        hook = read_hook_sidecar(root / entry.path, entry, source_package="<imported>")
    """
    restore_recorded_exec_bits(path, entry)
    body = entry.body if entry.body is not None else ""
    scripts = path.parent / "scripts"
    return Hook.from_dict(
        {
            "frontmatter": dict(entry.hook_frontmatter),
            "body": body,
            "template_body": body,
            "is_templated": bool(entry.is_templated),
            "source_path": str(path),
            "source_package": source_package,
            "scripts_dir": str(scripts) if scripts.is_dir() else None,
        }
    )


def copy_scripts(
    source: Path | None, dst_root: Path, repo_root: Path
) -> tuple[list[manifest.ScriptEntry], list[Path]]:
    """Byte-copy ``source``'s publishable files (never a secret or an escaping link).

    Bytecode caches are skipped too (``generated_output.source_files.skill_subtree_files``).
    Returns their manifest ``ScriptEntry`` records (repo-relative, with the
    source's exec bit) and the copied paths, through :func:`copy_script_files`.

    Example::

        scripts, paths = copy_scripts(hook.scripts_dir, hook_dir / "scripts", repo_root)
    """
    if source is None:
        return [], []
    pairs = [
        (src, dst_root / src.relative_to(source)) for src in copyable_skill_files(source, dst_root)
    ]
    return copy_script_files(pairs, repo_root)


def copy_script_files(
    pairs: Iterable[tuple[Path, Path]], repo_root: Path
) -> tuple[list[manifest.ScriptEntry], list[Path]]:
    """Byte-copy each ``(source, destination)`` pair, keeping the source's exec bit.

    Returns their manifest ``ScriptEntry`` records (repo-relative, with the exec
    bit) and the copied paths. A skill passes its published ``scripts/`` files
    (``published_skill_files``), so a file a failed ``applies_if`` withholds is
    never copied (prU D48, D58).

    Example::

        scripts, paths = copy_script_files(published_skill_files(skill, "scripts", dst), root)
    """
    scripts: list[manifest.ScriptEntry] = []
    paths: list[Path] = []
    for src, dst in pairs:
        executable = emitter.copy_script(src, dst)
        scripts.append(manifest.ScriptEntry(dst.relative_to(repo_root).as_posix(), executable))
        paths.append(dst)
    return scripts, paths


def guardrail_rules(hooks: Sequence[ResolvedHook]) -> list[Rule]:
    """The advisory rules (``guardrail-<id>``, priority 30) of the hooks that have one.

    Example: ``[r.frontmatter.id for r in guardrail_rules(hooks)] == ["guardrail-guard-x"]``.
    """
    return [hook.advisory for hook in hooks if hook.advisory is not None]


def stale_sidecar_candidates(repo_root: Path) -> list[Path]:
    """Every ``.playbook/hooks/<id>/HOOK.md`` on disk, for the sentinel scan.

    Only the sentinel-carrying ``HOOK.md`` files: copied scripts never carry
    one, and the lockfile leftover policy settles them (SPEC §4.2 step 9).

    Example: ``candidates.extend(stale_sidecar_candidates(repo_root))``.
    """
    return sorted((repo_root / HOOKS_SIDECAR).glob(f"*/{_MARKER}"))
