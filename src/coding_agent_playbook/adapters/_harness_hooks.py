"""Hooks in the agent_harness tree (specs/prK-lifecycle-hooks.md §C.6).

The Agent Harness spec has no lifecycle-event concept, so ``agent_harness`` is
advisory-only. It still keeps the ``playbook/hooks/`` -> harness ->
``import-harness`` round trip lossless:

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

from coding_agent_playbook.adapters._skill_sources import copyable_skill_files
from coding_agent_playbook.agent_harness import emitter, manifest
from coding_agent_playbook.artifacts.frontmatter import format_frontmatter
from coding_agent_playbook.generated_output.output_io import write_output_text

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.hook_policy import ResolvedHook

__all__ = [
    "HOOKS_SIDECAR",
    "copy_scripts",
    "emit_hook_sidecars",
    "guardrail_rules",
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
    write_output_text(target, emitter.with_sentinel_body(head, hook.template_body))
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


def copy_scripts(
    source: Path | None, dst_root: Path, repo_root: Path
) -> tuple[list[manifest.ScriptEntry], list[Path]]:
    """Byte-copy ``source``'s publishable files (never a secret or an escaping link).

    Bytecode caches are skipped too (``_skill_files.skill_subtree_files``).
    Returns their manifest ``ScriptEntry`` records (repo-relative, with the
    source's exec bit) and the copied paths. Shared by skills and hooks.

    Example::

        scripts, paths = copy_scripts(skill.scripts_dir, skill_dir / "scripts", repo_root)
    """
    if source is None:
        return [], []
    scripts: list[manifest.ScriptEntry] = []
    paths: list[Path] = []
    for src in copyable_skill_files(source, dst_root):
        dst = dst_root / src.relative_to(source)
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
