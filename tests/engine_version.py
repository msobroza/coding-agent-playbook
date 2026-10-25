"""The installed engine's version, the one value tests use for "the current engine".

Tests never spell the package version: a release bumps ``pyproject.toml`` alone,
and every fixture config, lockfile and pin follows (issue #283).
``tests/unit/test_engine_version_literals.py`` fails on a test file that writes it.

Example::

    config = CONFIG_TEMPLATE.replace("@ENGINE_VERSION@", ENGINE_VERSION)
"""

from __future__ import annotations

from typing import Final

from coding_agent_playbook import __version__

#: What ``importlib.metadata`` reports for this checkout (``0.0.0+local`` when never installed).
ENGINE_VERSION: Final[str] = __version__
