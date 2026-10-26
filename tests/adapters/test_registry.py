"""Tests for adapter discovery through the entry-point group (PR 10).

``installed_output_locations`` is tested with the adapters that declare those
locations (``test_shared_skills.py``, ``test_skill_writer.py``).
"""

from __future__ import annotations

from coding_agent_playbook.adapters.registry import discover_adapters
from coding_agent_playbook.config.model import Config, ProjectMeta, StorageConfig
from tests.engine_version import ENGINE_VERSION


def _make_config(adapters: list[str], overlays: list[str] | None = None) -> Config:
    return Config(
        schema_version=1,
        project=ProjectMeta(name="x", kind="python-library"),
        engine_version=ENGINE_VERSION,
        overlays_enabled=overlays or [],
        adapters_enabled=adapters,
        storage=StorageConfig(),
    )


def test_discover_adapters_always_includes_agents_md():
    """``agents_md`` must always be present even if not in adapters_enabled."""
    config = _make_config(adapters=["continue"])
    adapters = discover_adapters(config)
    assert "agents_md" in adapters
    assert "continue" in adapters


def test_discover_adapters_respects_enabled_list():
    config = _make_config(adapters=["claude_code"])
    adapters = discover_adapters(config)
    assert "claude_code" in adapters
    assert "continue" not in adapters
    assert "opencode" not in adapters
    assert "agents_md" in adapters  # always
