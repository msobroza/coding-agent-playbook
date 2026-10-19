"""Tests for the ``[links]`` table parser (SPEC §7.1, PR L)."""

from __future__ import annotations

import pytest


def test_parse_links_config_empty_uses_strict_default():
    from coding_agent_playbook.config.tables.links import parse_links_config

    cfg = parse_links_config({})
    assert cfg.allowed_domains == ()


def test_parse_links_config_lowercases_domains():
    from coding_agent_playbook.config.tables.links import parse_links_config

    cfg = parse_links_config({"allowed_domains": ["AgentHarnesses.IO", "example.com"]})
    assert cfg.allowed_domains == ("agentharnesses.io", "example.com")


def test_parse_links_config_rejects_non_list():
    from coding_agent_playbook.config.tables.links import parse_links_config

    with pytest.raises(ValueError, match="allowed_domains must be a list of strings"):
        parse_links_config({"allowed_domains": "example.com"})


def test_parse_links_config_rejects_non_string_entry():
    from coding_agent_playbook.config.tables.links import parse_links_config

    with pytest.raises(ValueError, match="allowed_domains must be a list of strings"):
        parse_links_config({"allowed_domains": ["ok.com", 42]})
