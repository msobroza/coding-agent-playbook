"""Environment checks run before ``playbook sync`` renders (SPEC §12.2, §13.1).

A sync that cannot see every configured overlay package silently renders
*without* it: ``FileSystemArtifactSource`` treats an unimportable package like
one that ships no artifacts. That is exactly what happens when the remote
``language: python`` pre-commit hooks run in pre-commit's isolated venv, which
holds only the engine at ``rev:`` — the post-checkout auto-sync would delete
the org rules and shrink the managed ``.gitignore`` block on every checkout.
So a missing overlay is a hard error (non-zero exit, package named, nothing
written). A missing *adapter* is only warned about: its old output is kept and
stays ignored (see ``_sync_orphans``), so nothing is lost or published.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_HOOK_VENV_HINT = (
    "A pre-commit hook from the engine's .pre-commit-hooks.yaml (language: python) runs in\n"
    "pre-commit's own venv: list the package under that hook's additional_dependencies, or\n"
    "use the repo: local + language: system hooks that 'playbook init' writes."
)


def missing_overlays(overlays: Sequence[str]) -> list[str]:
    """Return the configured overlay packages that cannot be imported here.

    Example::

        >>> missing_overlays(["json", "no_such_overlay_pkg"])
        ['no_such_overlay_pkg']
    """
    return [name for name in overlays if not _importable(name)]


def missing_adapters(enabled: Iterable[str], discovered: Iterable[str]) -> list[str]:
    """Return the enabled adapter names no installed entry point provides.

    Example::

        >>> missing_adapters(["continue", "codex"], ["continue", "agents_md"])
        ['codex']
    """
    return sorted(set(enabled) - set(discovered))


def report_missing_overlays(names: Sequence[str]) -> None:
    """Explain on stderr why the sync refused to run."""
    print(
        f"error: overlay package(s) in overlays_enabled are not importable: {', '.join(names)}.\n"
        "Rendering without them would drop their rules and un-ignore their output, so nothing\n"
        f"was written. Install them in the environment that runs 'playbook'.\n{_HOOK_VENV_HINT}",
        file=sys.stderr,
    )


def warn_missing_adapters(names: Sequence[str]) -> None:
    """Warn on stderr that enabled adapters were skipped (their old output is kept)."""
    print(
        f"warning: enabled adapter(s) not installed, skipped: {', '.join(names)}.\n"
        "Their previously generated output is kept (and stays gitignored) until they are\n"
        f"installed or removed from adapters_enabled.\n{_HOOK_VENV_HINT}",
        file=sys.stderr,
    )


def _importable(name: str) -> bool:
    """True when ``name`` resolves to an importable module (never imports it)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False
