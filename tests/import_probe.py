"""Fresh-interpreter import probes for the import-light tests (specs/prK-lifecycle-hooks.md §D.1).

A probe runs ``python -I -c <code>``, the hook runtime's own launch flags, so the
measured imports are the ones a hook process pays. Coverage's subprocess hooks
are scrubbed from the child env: pytest-cov exports ``COVERAGE_PROCESS_START`` /
``COV_CORE_*``, and coverage's ``a1_coverage.pth`` then imports coverage (and
``importlib.metadata`` with it) before the probe's first line. ``-I`` does not
help, because it only ignores ``PYTHON*`` variables.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys

PROBE_TIMEOUT_S = 60

#: Env-var prefixes that make a child interpreter start coverage at startup.
_COVERAGE_ENV_PREFIXES = ("COVERAGE_", "COV_CORE_")


def probe_env() -> dict[str, str]:
    """The current env minus coverage's subprocess-startup variables.

    Example::

        >>> "COVERAGE_PROCESS_START" in probe_env()
        False
    """
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(_COVERAGE_ENV_PREFIXES)
    }


def run_python_probe(code: str) -> str:
    """Run ``code`` in a fresh isolated interpreter and return its stripped stdout.

    Example::

        >>> run_python_probe("print(1 + 1)")
        '2'
    """
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        check=True,
        timeout=PROBE_TIMEOUT_S,
        env=probe_env(),
    )
    return completed.stdout.strip()


def new_modules_after(
    import_stmt: str, *, baseline: str = "import coding_agent_playbook"
) -> list[str]:
    """Modules ``import_stmt`` loads in a fresh interpreter beyond those ``baseline`` loaded.

    The default baseline is the package root, so the result is what a submodule
    costs on top of ``import coding_agent_playbook``.

    Example::

        >>> new_modules_after("import coding_agent_playbook.security.patterns")
        ['coding_agent_playbook.security', 'coding_agent_playbook.security.patterns']
    """
    code = (
        f"import sys; {baseline}; before = set(sys.modules); "
        f"{import_stmt}; print(sorted(set(sys.modules) - before))"
    )
    loaded: list[str] = ast.literal_eval(run_python_probe(code))
    return loaded
