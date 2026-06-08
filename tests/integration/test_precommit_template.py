"""The packaged air-gapped pre-commit starter renders to valid, all-local YAML.

Guards two things: the ``resources/precommit/config.yaml.j2`` template is
actually shipped (resolvable via ``importlib.resources``), and it renders
through the Jinja environment without a ``StrictUndefined`` error to a config
whose every hook is ``repo: local`` + ``language: system`` (so pre-commit never
clones a remote hook repo).
"""

from __future__ import annotations

import yaml

from coding_agent_playbook.commands.init import _render_fresh_pre_commit
from coding_agent_playbook.sources.filesystem import _resource_subdir


def test_precommit_template_is_packaged():
    precommit_dir = _resource_subdir("coding_agent_playbook", "precommit")
    assert precommit_dir is not None
    assert (precommit_dir / "config.yaml.j2").is_file()


def test_rendered_starter_is_air_gapped_yaml():
    rendered = _render_fresh_pre_commit()
    assert "https://" not in rendered  # nothing to clone

    parsed = yaml.safe_load(rendered)
    assert isinstance(parsed, dict)
    repos = parsed["repos"]
    assert isinstance(repos, list) and repos

    for entry in repos:
        assert entry["repo"] == "local"
        for hook in entry["hooks"]:
            assert hook["language"] == "system"

    ids = {hook["id"] for entry in repos for hook in entry["hooks"]}
    assert {"coding-agent-playbook-sync", "ruff", "ruff-format", "mypy"} <= ids
