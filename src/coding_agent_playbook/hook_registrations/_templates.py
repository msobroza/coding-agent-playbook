"""The packaged hook-shim templates under ``templates/hook_shims/`` (specs/prK-lifecycle-hooks.md §C.3.1).

The Claude Code launcher and the OpenCode plugin are rendered by ``str.replace``
of fixed placeholders, never Jinja (L7): shell and JS braces would fight it, and
nothing a hook author writes ever reaches a template. Like the pre-commit
template (``templates/precommit/``), they are engine wiring, not playbook
content: they stay in the package, outside the bundled ``catalog/`` tree, so
``FileSystemArtifactSource`` never walks them and no layer can override them.
"""

from __future__ import annotations

from importlib import resources
from typing import Final

__all__ = ["SENTINEL_PLACEHOLDER", "fill_placeholder", "shim_template"]

#: Line 1 of every template: replaced by the engine sentinel in the file's comment style.
SENTINEL_PLACEHOLDER: Final = "@@SENTINEL_LINE@@"
_TEMPLATE_DIR: Final = ("templates", "hook_shims")


def shim_template(name: str) -> str:
    """The text of ``templates/hook_shims/<name>``, line endings read as LF.

    Text mode reads a CRLF checkout (``core.autocrlf``) back as LF, so every
    clone renders the same bytes.

    Example: ``shim_template("claude-launch.sh").startswith(SENTINEL_PLACEHOLDER)``.
    """
    template = resources.files("coding_agent_playbook").joinpath(*_TEMPLATE_DIR, name)
    return template.read_text(encoding="utf-8")


def fill_placeholder(template: str, placeholder: str, value: str) -> str:
    """``template`` with its one ``placeholder`` replaced by ``value``.

    Raises ValueError, naming the placeholder and its count, unless it occurs
    exactly once: a lost or duplicated placeholder would ship a shim that
    fails to load, which OpenCode only logs (§C.3.7).

    Example: ``fill_placeholder("a = X", "X", "1") == "a = 1"``.
    """
    count = template.count(placeholder)
    if count != 1:
        raise ValueError(
            f"hook shim template must contain {placeholder!r} exactly once, found {count}"
        )
    return template.replace(placeholder, value)
