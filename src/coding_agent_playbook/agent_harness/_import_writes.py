"""The file side of ``playbook import-harness``: the overlay writes and their file helpers.

:func:`~.importer.write_import` writes each kind through this module in the
:class:`~coding_agent_playbook.catalog.source.FileSystemArtifactSource` layout, so
a later ``playbook sync`` re-reads it. The readers share its file helpers: a
harness ``.md`` split into frontmatter and a sentinel-stripped body, the harness
root behind a manifest path, and the exec bits that skills and hooks both restore
(``specs/prH-agent-harness.md`` decision #1, specs/prK-lifecycle-hooks.md §C.6).
Absorbs AH-1's ``_import_files.py`` and the write half of ``_import_hooks.py`` (AH-2, #143).
"""

from __future__ import annotations

import dataclasses
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.artifacts.frontmatter import format_frontmatter, split_frontmatter
from coding_agent_playbook.artifacts.member_reference import skill_member_path
from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.generated_output.source_files import skill_subtree_files

if TYPE_CHECKING:
    from collections.abc import Collection

    from coding_agent_playbook.agent_harness.manifest import ManifestEntry
    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

_SENTINEL_PREFIX = f"{sentinel_line('html')}\n\n"


# --- reading a harness file ------------------------------------------------


def strip_sentinel(body: str) -> str:
    """Drop the leading ``<!-- SENTINEL -->`` line the emitter places (no-op without one).

    The adapter writes the sentinel as the first body line (frontmatter must stay
    on line 1); a foreign harness has none.

    Example: ``strip_sentinel(leaf.body)``.
    """
    if body.startswith(_SENTINEL_PREFIX):
        return body[len(_SENTINEL_PREFIX) :]
    return body


def read_harness_md(path: Path) -> tuple[dict[str, Any], str]:
    """Split a harness ``.md`` into (frontmatter, sentinel-stripped body).

    A foreign harness's content file may carry no frontmatter (``description`` is
    optional): the whole text is then the body, and this never raises on it.

    Example: ``frontmatter, body = read_harness_md(root / "rules" / "50-style.md")``.
    """
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, raw_body = split_frontmatter(text)
    except ValueError:
        return {}, strip_sentinel(text)
    return frontmatter, strip_sentinel(raw_body)


def harness_root_for(absolute: Path, relative: str) -> Path:
    """Recover the harness root: ``absolute`` minus its harness-relative tail.

    Example: ``harness_root_for(Path("/h/skills/x/SKILL.md"), "skills/x/SKILL.md") == Path("/h")``.
    """
    root = absolute
    for _ in Path(relative).parts:
        root = root.parent
    return root


def restore_exec_bit(path: Path) -> None:
    """Set the execute bit on POSIX (no-op on Windows / missing file).

    Example: ``restore_exec_bit(harness_root / script.path)``.
    """
    if os.name != "posix" or not path.is_file():
        return
    os.chmod(path, os.stat(path).st_mode | 0o111)


def restore_recorded_exec_bits(path: Path, entry: ManifestEntry) -> None:
    """Give back the exec bit of every script ``entry`` records as executable.

    ``path`` is the entry's own file in the tree; script paths are harness-relative.
    A transport (zip, Windows checkout) may have dropped the bits since emission.

    Example: ``restore_recorded_exec_bits(root / entry.path, entry)``.
    """
    harness_root = harness_root_for(path, entry.path)
    for script in entry.scripts:
        if script.executable:
            restore_exec_bit(harness_root / script.path)


# --- writing the overlay ---------------------------------------------------


def copy_tree(src: Path, dst: Path, *, restore_exec: bool) -> None:
    """Copy ``src`` files into ``dst`` verbatim, preserving the executable bit.

    Bytecode caches are skipped by the same rule sync uses, so running a harness
    script never plants ``__pycache__`` in the canonical ``playbook/skills/``
    (or a hook's ``scripts/``).

    Example: ``copy_tree(skill.scripts_dir, skill_dir / "scripts", restore_exec=True)``.
    """
    for path in skill_subtree_files(src):
        out = dst / path.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
        if restore_exec and os.name == "posix" and (os.stat(path).st_mode & 0o111):
            restore_exec_bit(out)


def write_rule(rule: Rule, into: Path, *, skill_ids: Collection[str] = ()) -> None:
    """Write ``rule`` where the catalog loader reads it back (``.md.j2`` when templated).

    A rule placed by location (``home_skill`` set) whose skill is in
    ``skill_ids``, the skills imported with it from the same harness, goes to
    ``<into>/skills/<skill>/rules/<id>.md`` without a ``skill:`` line (prU D22,
    D5). Every other rule, always or scoped, goes to ``<into>/rules/<id>.md``,
    keeping its ``skill:``: a scoped rule written to ``references/`` would be
    dropped by the next sync.

    Example: ``write_rule(rule, Path("playbook"))`` -> ``playbook/rules/style.md``.
    """
    suffix = ".md.j2" if rule.is_templated else ".md"
    home = rule.home_skill
    if home is not None and home in skill_ids:
        target = into / skill_member_path(home, rule.frontmatter.id, suffix=suffix)
    else:
        target = into / "rules" / f"{rule.frontmatter.id}{suffix}"
        rule = dataclasses.replace(rule, skill_from_location=False)  # spell the skill out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rule.to_markdown(), encoding="utf-8")


def write_prompt(prompt: Prompt, into: Path) -> None:
    """Write ``prompt`` as ``<into>/prompts/<id>.md`` (``.md.j2`` when templated).

    Example: ``write_prompt(prompt, Path("playbook"))`` -> ``playbook/prompts/review.md``.
    """
    suffix = ".md.j2" if prompt.is_templated else ".md"
    target = into / "prompts" / f"{prompt.frontmatter.id}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(prompt.to_markdown(), encoding="utf-8")


def write_skill(skill: Skill, into: Path) -> None:
    """Write ``<into>/skills/<id>/SKILL.md`` with the full frontmatter, plus its side dirs.

    The side dirs are ``scripts/`` (exec bits restored), ``references/`` and
    ``examples/`` (prU D48).

    Example: ``write_skill(skill, Path("playbook"))`` -> ``playbook/skills/db/SKILL.md``.
    """
    skill_id = str(skill.frontmatter.get("id", "skill"))
    skill_dir = into / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    text = format_frontmatter(dict(skill.frontmatter), skill.body)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    for name, src in skill.side_dirs():
        if src is not None and src.is_dir():
            copy_tree(src, skill_dir / name, restore_exec=name == "scripts")


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


def write_raw_asset(asset: Path, into: Path) -> None:
    """Copy a raw (non-markdown) asset verbatim to ``<into>/references/<name>``.

    Example: ``write_raw_asset(Path("h/references/logo.png"), Path("playbook"))``.
    """
    target = into / "references" / asset.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(asset, target)
