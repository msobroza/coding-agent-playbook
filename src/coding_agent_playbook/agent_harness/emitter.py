"""Pure emit helpers for the ``agent_harness`` output adapter (Track H1).

These functions build harness file *contents* and names (strings) and perform
the single filesystem side effect the adapter delegates here — copying a script
verbatim with :func:`shutil.copy2` while reporting its executable bit. Keeping the
string builders pure makes the adapter's ``finalize`` easy to unit-test; AH-2
(#143) moved the adapter's stateless builders (``HARNESS.md``, the always-rule
file name, the skill-directory test) here.

Invariants honoured (``specs/prH-agent-harness.md`` §B + CLAUDE.md):

- Frontmatter MUST stay on line 1 (``^---``) for a harness parser to match it,
  so the playbook :data:`SENTINEL` is emitted as the **first body line**, never
  line 1, as an HTML comment.
- Scripts are byte-copied (copies, not symlinks); their exec bit is reported so
  the adapter can record it in the sidecar manifest.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import yaml

from coding_agent_playbook.agent_harness.leaf_detectors import HARNESS_LEAF_MARKER
from coding_agent_playbook.generated_output.output_io import copy_output
from coding_agent_playbook.rendering.formats import with_sentinel_body

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule

_FENCE = "---"
_HARNESS_MD_INTRO = (
    "This harness provides the coding rules, prompts and skills for this "
    "project. Consult the routing files in each directory for details."
)


def frontmatter_block(fields: Mapping[str, str]) -> str:
    """Render ``fields`` as a YAML ``--- ... ---`` frontmatter block.

    Key order is preserved (``sort_keys=False``). The returned block starts with
    ``---`` on line 1 and ends with a trailing newline after the closing fence.
    """
    dumped = yaml.safe_dump(dict(fields), sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"{_FENCE}\n{dumped}\n{_FENCE}\n"


def routing_file(description: str, body: str) -> str:
    """Build a routing-file string: ``description``-only frontmatter + body.

    Routing files carry no ``name`` field (only grouping-dir ``description``),
    and carry the playbook sentinel as their first body line.
    """
    return with_sentinel_body(frontmatter_block({"description": description}), body)


def leaf_detectors_file(types: Mapping[str, str]) -> str:
    """Render a ``.leaf-detectors`` file body from a ``{leaf_type: path}`` map.

    One ``leaf_type=relative_path`` rule per line, in insertion order. This file
    is not frontmatter-fenced and carries no sentinel (it is a config dotfile).
    """
    return "".join(f"{key}={value}\n" for key, value in types.items())


def harnessleaf_path(directory: Path) -> Path:
    """Return the path of the ``.harnessleaf`` marker inside ``directory``."""
    return directory / HARNESS_LEAF_MARKER


def copy_script(src: Path, dst: Path) -> bool:
    """Copy ``src`` to ``dst`` verbatim (``shutil.copy2``), creating parents.

    Returns whether the **source** file had any execute bit set on disk. The
    adapter records this in the sidecar manifest so the importer can restore the
    bit on POSIX regardless of how the harness was transported (decision #1).
    """
    executable = bool(os.stat(src).st_mode & 0o111)
    dst.parent.mkdir(parents=True, exist_ok=True)
    copy_output(src, dst)
    return executable


def always_rule_filename(rule: Rule) -> str:
    """The ``rules/`` file name of an always-rule: its two-digit priority, then its id.

    Example: ``always_rule_filename(rule) == "10-python-house-style.md"`` (priority 10).
    """
    return f"{rule.frontmatter.priority:02d}-{rule.frontmatter.id}.md"


def harness_md_text(name: str, emitted_dirs: Sequence[str], always_rules: Sequence[Rule]) -> str:
    """The whole ``HARNESS.md``: frontmatter, sentinel, the contents index and the always-rules.

    ``emitted_dirs`` are the top-level directories this render writes, in index
    order: never what happens to be on disk, or a leftover ``skills/`` would make
    ``sync --check`` (rendering into an empty scratch) drift. The always-rules are
    listed by (priority, id).

    Example: ``harness_md_text("repo", ["skills", "rules"], always_rules)``.
    """
    description = f"Coding-agent harness for {name}."
    frontmatter = frontmatter_block({"name": name, "description": description})
    sections = [f"# {name}", "", _HARNESS_MD_INTRO, "", "## Contents", ""]
    sections.extend(f"- `{d}/` — see `{d}/{d.upper()}.md`" for d in emitted_dirs)
    sections.append("")
    if always_rules:
        sections.extend(_always_consult_lines(always_rules))
    return with_sentinel_body(frontmatter, "\n".join(sections))


def _always_consult_lines(always_rules: Sequence[Rule]) -> list[str]:
    """The ``## Always consult these`` section: one pointer per always-rule file."""
    ordered = sorted(always_rules, key=lambda r: (r.frontmatter.priority, r.frontmatter.id))
    intro = ["## Always consult these", "", "Read these rules at the start of every session:", ""]
    pointers = [
        f"- `rules/{always_rule_filename(rule)}` — {rule.frontmatter.description}"
        for rule in ordered
    ]
    return [*intro, *pointers, ""]


def inside_skill_dir(path: Path, skills_dir: Path) -> bool:
    """True for ``skills/<id>/...`` (a skill's own files), False for ``skills/SKILLS.md``.

    Example: ``inside_skill_dir(repo / "skills" / "db" / "SKILL.md", repo / "skills") is True``.
    """
    try:
        return len(path.relative_to(skills_dir).parts) > 1
    except ValueError:
        return False
