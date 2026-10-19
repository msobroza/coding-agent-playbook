"""``FileSystemStateSource.load_policy_tables``: the committed file only (§B.1).

It reads ``[hooks]`` / ``[guardrails]`` from the committed config, never from
``.coding-agent-playbook.local.toml``. Split out of the hook discovery tests
(N3), which moved to ``tests/catalog/test_source_hooks.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.config.tables.hooks import PolicyTables

if TYPE_CHECKING:
    from pathlib import Path


_COMMITTED_CONFIG = """\
schema_version = 1

[project]
name = "x"
kind = "python-library"

[engine]
version = "0.1"
"""

_COMMITTED_POLICY = """
[hooks]
enabled = true
disable = ["guard-x"]

[guardrails.git]
protected_branches = ["develop"]
"""

_LOCAL_POLICY = """\
[user_choices]
style = "google"

[hooks]
enabled = false

[guardrails.network]
mode = "off"
"""


def _state_source(repo: Path, *, committed: str, local: str | None = None) -> FileSystemStateSource:
    (repo / ".coding-agent-playbook.toml").write_text(committed, encoding="utf-8")
    if local is not None:
        (repo / ".coding-agent-playbook.local.toml").write_text(local, encoding="utf-8")
    return FileSystemStateSource(repo_root=repo)


def test_load_policy_tables_ignores_local_toml_hooks_and_guardrails(tmp_path: Path) -> None:
    source = _state_source(
        tmp_path, committed=_COMMITTED_CONFIG + _COMMITTED_POLICY, local=_LOCAL_POLICY
    )

    tables = source.load_policy_tables()

    assert tables.hooks == {"enabled": True, "disable": ["guard-x"]}
    assert tables.guardrails == {"git": {"protected_branches": ["develop"]}}
    # The deep-merged view would have let the gitignored file switch hooks off.
    assert source.load_config().extra_tables["hooks"]["enabled"] is False


def test_load_policy_tables_reports_local_policy_keys(tmp_path: Path) -> None:
    source = _state_source(tmp_path, committed=_COMMITTED_CONFIG, local=_LOCAL_POLICY)

    tables = source.load_policy_tables()

    assert tables.local_keys == ("hooks.enabled", "guardrails.network.mode")
    assert (tables.hooks, tables.guardrails) == (None, None)


def test_load_policy_tables_without_policy_tables_is_empty(tmp_path: Path) -> None:
    source = _state_source(tmp_path, committed=_COMMITTED_CONFIG)

    assert source.load_policy_tables() == PolicyTables()
