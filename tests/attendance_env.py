"""The environment variables that mark a hook run unattended (specs/prK-lifecycle-hooks.md §D.3.6).

``hook_runtime.dispatch.policy.is_unattended`` turns every ``ask`` into a ``deny`` when
one of these is set, and CI runners export them to every step (GitHub Actions:
``CI=true``, ``GITHUB_ACTIONS=true``). A test that inherits them runs the
unattended path by accident, on CI only. So the suite never inherits them:
``tests.import_probe.probe_env`` drops them from every spawned dispatcher's
env, and the root conftest clears them from ``os.environ`` for the session. A
test that wants an unattended run sets one deliberately
(``runtime_deps(env={"CI": "true"})``, ``monkeypatch.setenv``).

Stdlib-only: the root conftest imports it, and must not load the hook runtime.
``tests/hook_runtime/test_attendance_env.py`` pins the names to the keys
``is_unattended`` reads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["ATTENDANCE_ENV_VARS", "without_attendance_vars"]

#: Every env key ``is_unattended`` reads (``policy.UNATTENDED_ENV_VAR`` first).
ATTENDANCE_ENV_VARS: Final = ("PLAYBOOK_HOOK_UNATTENDED", "CI", "GITHUB_ACTIONS")


def without_attendance_vars(env: Mapping[str, str]) -> dict[str, str]:
    """A copy of ``env`` without :data:`ATTENDANCE_ENV_VARS`: a hook spawned with it runs attended.

    Example::

        >>> without_attendance_vars({"CI": "true", "PATH": "/usr/bin"})
        {'PATH': '/usr/bin'}
    """
    return {name: value for name, value in env.items() if name not in ATTENDANCE_ENV_VARS}
