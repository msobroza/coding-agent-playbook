"""Pure emit helpers for the ``agent_harness`` output adapter (Track H1).

These functions build harness file *contents* (strings) and perform the single
filesystem side effect the adapter delegates here — copying a script verbatim
with :func:`shutil.copy2` while reporting its executable bit. Keeping the string
builders pure makes the adapter's ``finalize`` easy to unit-test.

Invariants honoured (``specs/prH-agent-harness.md`` §B + CLAUDE.md):

- Frontmatter MUST stay on line 1 (``^---``) for a harness parser to match it,
  so the playbook :data:`SENTINEL` is emitted as the **first body line**, never
  line 1, as an HTML comment.
- Scripts are byte-copied (copies, not symlinks); their exec bit is reported so
  the adapter can record it in the sidecar manifest.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import yaml

from coding_agent_playbook.agent_harness.leaf_detectors import HARNESS_LEAF_MARKER
from coding_agent_playbook.generated_output.output_io import copy_output
from coding_agent_playbook.rendering.formats import with_sentinel_body

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

_FENCE = "---"


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


def input_variables_note(variables: Sequence[Mapping[str, Any]]) -> str:
    """A ``## Input variables`` list telling the agent what to substitute; ``""`` without any.

    Example::

        >>> input_variables_note([{"name": "path", "description": "file to review"}])
        '## Input variables\\n\\n- `path` — file to review\\n'
    """
    if not variables:
        return ""
    lines = ["## Input variables", ""]
    for var in variables:
        varname = str(var.get("name", ""))
        desc = str(var.get("description", "")).strip()
        lines.append(f"- `{varname}`" + (f" — {desc}" if desc else ""))
    return "\n".join(lines) + "\n"


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
