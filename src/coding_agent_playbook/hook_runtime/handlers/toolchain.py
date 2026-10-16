"""toolchain-missing-hint: a reactive hint when the dev toolchain is missing (specs/prK-hook-pack.md §E.3).

Default, ``post_tool_use`` + ``post_tool_use_failure`` on ``Bash``. In Claude
Code a non-zero exit arrives as ``PostToolUseFailure`` whose ``error`` starts
``Exit code N``, so the failure is the primary path; a successful call's
output is scanned too (a later segment can hide an earlier
``command not found``). One regex over the text: ``No module named
mypy|pytest|ruff|commitizen`` or ``ruff|mypy|pytest|cz: command not found``.

Once per session per tool it tells the model how the project installs its
dev tooling (``install_hint``, derived at sync from the package manager and
the dev extra or group) and to ask the user first: an install may contact the
package index. It never runs the install, and is silent otherwise. It replaces
a session-start toolchain probe, which would have needed a venv probe (and a
``uv run`` that may sync) at every start. ``on_error: open``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.registry import register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = ["CZ_FALLBACK_HINT", "missing_tool", "toolchain_hint"]

#: commitizen is a user-level tool when the project does not pin it (§F.4).
CZ_FALLBACK_HINT: Final = "pipx install commitizen"
#: The last 8 KiB of the output (``ToolResponse.output`` keeps no more).
SCAN_CHARS: Final = 8_192
_MISSING: Final = re.compile(
    r"No module named '?(?P<module>mypy|pytest|ruff|commitizen)\b"
    r"|\b(?P<command>ruff|mypy|pytest|cz): command not found"
    r"|command not found: (?P<zsh>ruff|mypy|pytest|cz)\b"
)
#: The module name of a tool whose command differs.
_COMMAND_OF: Final[Mapping[str, str]] = {"commitizen": "cz"}


@register_hook_handler(
    "toolchain_hint",
    events=["post_tool_use", "post_tool_use_failure"],
    decisions=["context", "none"],
)
def toolchain_hint(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Name the project's install command, once per session per missing tool.

    Example::

        >>> toolchain_hint(failure_no_module_mypy, ctx).context  # doctest: +SKIP
        ('Dev tooling is not installed in this environment (`mypy` is missing). ...',)
    """
    response = None if ev.tool is None else ev.tool.response
    if response is None:
        return None
    tool = missing_tool(response.error if not response.ok else response.output)
    if tool is None or not ctx.session.once(f"toolchain:{tool}"):
        return None
    return HandlerResult(
        decision=Decision.CONTEXT,
        hook_id=ctx.hook.id,
        rule_id=f"toolchain_{tool}",
        context=(_hint(tool, ctx.config),),
    )


def missing_tool(text: str | None) -> str | None:
    """The dev tool ``text`` says is missing (its command name), else ``None``.

    Example::

        >>> missing_tool("Exit code 1\\n/usr/bin/python3: No module named mypy")
        'mypy'
    """
    if not text:
        return None
    found = _MISSING.search(text[-SCAN_CHARS:])
    if found is None:
        return None
    name = found.group("module") or found.group("command") or found.group("zsh")
    return _COMMAND_OF.get(name, name)


def _hint(tool: str, config: Mapping[str, object]) -> str:
    hint = config.get("cz_install_hint" if tool == "cz" else "install_hint")
    if isinstance(hint, str) and hint:
        return (
            f"Dev tooling is not installed in this environment (`{tool}` is missing). "
            f"The project installs it with `{hint}`. Ask the user before installing "
            "(it may contact the package index)."
        )
    if tool == "cz":
        return (
            "`cz` (commitizen) is not installed in this environment and the project does not "
            f"pin it. Ask the user to install commitizen (`{CZ_FALLBACK_HINT}`)."
        )
    return (
        f"Dev tooling is not installed in this environment (`{tool}` is missing). "
        "Ask the user how the project installs it; do not install it yourself."
    )
