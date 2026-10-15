"""Hooks in ``playbook import-harness`` (specs/prK-lifecycle-hooks.md §C.6).

Lossless: a manifest entry of kind ``hook`` rebuilds the canonical ``Hook``
from the sidecar's ``hook_frontmatter``, ``body`` and ``is_templated`` (never
from the rendered advisory), restoring script exec bits, and is written back
in the repo-local layout ``<into>/hooks/<id>/HOOK.md(.j2)`` + ``scripts/``.
Best-effort (no sidecar): a ``guardrail-*`` rule file is only a degraded
advisory, so its import as a ``Rule`` is flagged as lossy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook._hook_schema import ADVISORY_RULE_PREFIX
from coding_agent_playbook.commands._import_files import copy_tree, restore_exec_bit
from coding_agent_playbook.types import Hook

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.harness.manifest import ManifestEntry

__all__ = ["guardrail_warning", "hook_from_entry", "write_hook"]


def hook_from_entry(
    path: Path, entry: ManifestEntry, *, harness_root: Path, source_package: str
) -> Hook:
    """Rebuild the ``Hook`` recorded by ``entry`` (its sidecar ``HOOK.md`` is ``path``).

    Raises ``HookSchemaError`` (naming the field and value) when the recorded
    frontmatter no longer parses; the importer reports it and skips the entry.

    Example::

        hook = hook_from_entry(root / entry.path, entry, harness_root=root,
                               source_package="<imported>")
    """
    for script in entry.scripts:
        if script.executable:
            restore_exec_bit(harness_root / script.path)
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


def write_hook(hook: Hook, into: Path) -> Path:
    """Write ``hook`` as ``<into>/hooks/<id>/HOOK.md`` (``.md.j2`` when templated) + ``scripts/``.

    Example: ``write_hook(hook, Path("playbook"))`` -> ``playbook/hooks/guard-x/HOOK.md``.
    """
    hook_dir = into / "hooks" / hook.frontmatter.id
    hook_dir.mkdir(parents=True, exist_ok=True)
    target = hook_dir / ("HOOK.md.j2" if hook.is_templated else "HOOK.md")
    target.write_text(hook.to_markdown(), encoding="utf-8")
    if hook.scripts_dir is not None and hook.scripts_dir.is_dir():
        copy_tree(hook.scripts_dir, hook_dir / "scripts", restore_exec=True)
    return target


def guardrail_warning(rule_id: str) -> str | None:
    """The lossiness warning for a best-effort rule that is really a hook advisory, else None.

    Example::

        >>> guardrail_warning("guardrail-x") is not None, guardrail_warning("typing")
        (True, None)
    """
    if not rule_id.startswith(ADVISORY_RULE_PREFIX):
        return None
    return (
        f"rule {rule_id!r}: looks like a degraded hook advisory; the canonical hook "
        "cannot be reconstructed without .playbook/manifest.toml"
    )
