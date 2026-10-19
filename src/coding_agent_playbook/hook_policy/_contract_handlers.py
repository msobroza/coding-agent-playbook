"""The handler half of the hook trust contract: H6, H7 and H13 (specs/prK-lifecycle-hooks.md §B.5).

- H6: exactly one of ``handler`` / ``handlers``; ``handlers`` keys equal
  ``events``; each handler has exactly one form; a builtin name is snake_case,
  ``<name>:<role>`` for a companion. Whether the name is registered, its config
  matches its ``CONFIG_SCHEMA``, its decisions and ``MUTATES_INPUT`` are the
  registry's half, which K2 closes.
- H7: an external handler runs a known launcher on a regular file under
  ``scripts/`` contained in the hook directory (no symlink on the way), with
  static args (no ``://``) and a JSON-serializable config; ``scripts/`` exists
  only for external handlers.
- H13: engine hooks are builtin-only and ship no ``scripts/``: engine Python
  lives in ``src/``, under the CI-parity gate.

Split out of :mod:`.contract` for the file-size budget.
"""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final, get_args

from coding_agent_playbook.artifacts.hook_schema import HookLauncher
from coding_agent_playbook.hook_policy._findings import Finding, error

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
    from coding_agent_playbook.artifacts.hook_schema import HookHandler

#: The launchers an external handler may name (§A.2); never a shell string.
LAUNCHERS: Final[tuple[str, ...]] = get_args(HookLauncher)

#: snake_case, plus ``:<role>`` for a companion on a second event (lock K-2).
_BUILTIN_NAME: Final = re.compile(r"[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*)?")
_SCRIPTS: Final = "scripts"
_FORM: Final = "exactly one form: builtin, or command + script (+ args)"


def handler_slots(frontmatter: HookFrontmatter) -> list[tuple[str, HookHandler]]:
    """Each authored handler with its frontmatter label: ``handler`` or ``handlers.<event>``.

    Example: ``handler_slots(fm) == [("handler", fm.handler)]`` for a one-handler hook.
    """
    shared = [] if frontmatter.handler is None else [("handler", frontmatter.handler)]
    return [*shared, *((f"handlers.{e}", h) for e, h in frontmatter.handlers.items())]


def handler_findings(hook: Hook, *, engine_sourced: bool) -> list[Finding]:
    """Every H6/H7/H13 finding of ``hook``; ``engine_sourced`` enables H13.

    Example::

        >>> handler_findings(sample_hook(), engine_sourced=False)  # doctest: +SKIP
        []
    """
    slots = handler_slots(hook.frontmatter)
    findings = list(_binding_findings(hook.frontmatter))
    for label, handler in slots:
        findings.extend(_form_findings(label, handler))
        if handler.builtin is None:
            findings.extend(_external_findings(hook, label, handler))
    if hook.scripts_dir is not None and all(h.builtin is not None for _, h in slots):
        findings.append(
            error(
                "scripts/ exists but no handler is external; "
                "only an external handler may ship scripts"
            )
        )
    if engine_sourced:
        findings.extend(_engine_findings(hook, slots))
    return findings


def _binding_findings(fm: HookFrontmatter) -> Iterator[Finding]:
    """H6: one of handler/handlers, and handlers keyed by exactly the events."""
    if fm.handler is not None and fm.handlers:
        yield error("exactly one of handler / handlers is required, got both")
    elif fm.handler is None and not fm.handlers:
        yield error("exactly one of handler / handlers is required, got neither")
    elif fm.handlers:
        missing = [event for event in dict.fromkeys(fm.events) if event not in fm.handlers]
        unexpected = [event for event in fm.handlers if event not in fm.events]
        parts = [
            *([f"missing {missing!r}"] if missing else []),
            *([f"unexpected {unexpected!r}"] if unexpected else []),
        ]
        if parts:
            yield error(f"handlers: keys must equal events exactly; {', '.join(parts)}")


def _form_findings(label: str, handler: HookHandler) -> Iterator[Finding]:
    """H6: a builtin with no external keys and a snake_case name, or command + script."""
    if handler.builtin is None:
        missing = [key for key in ("command", "script") if not getattr(handler, key)]
        if missing:
            yield error(
                f"{label}: an external handler needs both command and script; "
                f"missing {', '.join(missing)}"
            )
        return
    external = [key for key in ("command", "script", "args") if getattr(handler, key)]
    if external:
        yield error(f"{label}: {_FORM}; got builtin {handler.builtin!r} with {', '.join(external)}")
    if _BUILTIN_NAME.fullmatch(handler.builtin) is None:
        yield error(
            f"{label}.builtin {handler.builtin!r} must be snake_case, "
            "or '<name>:<role>' for a companion"
        )


def _external_findings(hook: Hook, label: str, handler: HookHandler) -> Iterator[Finding]:
    """H7: launcher, contained script, static args, JSON-serializable config."""
    if handler.command and handler.command not in LAUNCHERS:
        yield error(
            f"{label}.command {handler.command!r} is not a launcher; "
            f"allowed: {', '.join(LAUNCHERS)}"
        )
    if handler.script:
        yield from _script_findings(hook, label, handler.script)
    for arg in handler.args:
        if "://" in arg:
            yield error(f"{label}.args: {arg!r} must not contain '://' (static args only)")
    try:
        # allow_nan=False: NaN/Infinity are not JSON, and the script reads JSON.
        json.dumps(handler.config, allow_nan=False)
    except (TypeError, ValueError) as exc:
        yield error(
            f"{label}.config is not JSON-serializable (it is passed to the script as JSON): {exc}"
        )


def _script_findings(hook: Hook, label: str, script: str) -> Iterator[Finding]:
    shown = f"{label}.script {script!r}"
    path = PurePosixPath(script)
    if path.is_absolute() or ".." in path.parts:
        yield error(f"{shown} escapes the hook directory")
        return
    if "\\" in script or len(path.parts) < 2 or path.parts[0] != _SCRIPTS:
        yield error(f"{shown} must be a relative POSIX path under scripts/")
        return
    problem = None if hook.hook_dir is None else _on_disk_problem(hook.hook_dir, path.parts)
    if problem is not None:
        yield error(f"{shown} {problem}")


def _on_disk_problem(hook_dir: Path, parts: tuple[str, ...]) -> str | None:
    """Why ``<hook_dir>/<parts>`` is not a contained regular file, or None when it is.

    Every component is checked for a symlink, like ``links.classify_link``'s
    containment idiom: a linked ``scripts/`` would let the copy pull in
    anything, and the trust hash would cover bytes outside the hook.
    """
    path = hook_dir
    for part in parts:
        path = path / part
        if path.is_symlink():
            return "is a symlink; copy the file into the hook directory"
    try:
        contained = path.resolve().is_relative_to(hook_dir.resolve())
    except (OSError, RuntimeError):  # a loop, or a component that vanished
        return "cannot be resolved"
    if not contained:
        return "escapes the hook directory"
    return None if path.is_file() else "is not a regular file"


def _engine_findings(hook: Hook, slots: list[tuple[str, HookHandler]]) -> Iterator[Finding]:
    """H13: engine hooks are builtin-only and ship no scripts/."""
    for label, handler in slots:
        if handler.builtin is None:
            yield error(f"engine hooks are builtin-only; {label} is an external command")
    if hook.scripts_dir is not None:
        yield error("engine hooks ship no scripts/ directory")
