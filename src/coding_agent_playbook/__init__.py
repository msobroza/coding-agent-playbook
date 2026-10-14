"""coding-agent-playbook engine — see SPEC.md for the design.

``__version__`` is computed lazily (PEP 562): ``importlib.metadata`` costs most
of a cold package import, and the hook runtime imports this package on every
tool call within a 100 ms budget (specs/prK-lifecycle-hooks.md §D.1, P-D1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Declared for type checkers and ruff F822; the value comes from __getattr__.
    __version__: str

__all__ = ["__version__"]

_DISTRIBUTION = "coding-agent-playbook"
#: Reported by a source checkout that was never installed.
_LOCAL_VERSION = "0.0.0+local"


def __getattr__(name: str) -> str:
    """Resolve ``__version__`` on first access and cache it in the module globals.

    Example::

        >>> import coding_agent_playbook
        >>> coding_agent_playbook.__version__  # doctest: +SKIP
        '0.1.0a0'
    """
    if name != "__version__":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib.metadata import PackageNotFoundError, version

    try:
        resolved = version(_DISTRIBUTION)
    except PackageNotFoundError:
        resolved = _LOCAL_VERSION
    globals()["__version__"] = resolved
    return resolved
