"""Tests for the SPEC §12.6 self-contained-markdown-links rule (PR L).

Drives ``playbook validate`` end-to-end on synthetic consumer repos, plus the
CI gate asserting every *shipped* engine artifact is itself clean — that test
running under ``pytest -q`` is what enforces the invariant on CI.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import _validate_links
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.links import LinksConfig
from coding_agent_playbook.packs.superpowers import PACK_NAME
from coding_agent_playbook.sources.base import ArtifactSource
from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource, _resource_subdir
from coding_agent_playbook.types import Prompt, PromptFrontmatter
from tests.packs.superpowers_expectations import SKILLS_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.types import Rule, Skill


def _ns(repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo))


_ALLOWLIST_CONFIG = """\
schema_version = 1
adapters_enabled = ["continue", "claude_code", "opencode"]
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"

[links]
allowed_domains = ["example.com"]
"""

_BAD_LINKS_CONFIG = _ALLOWLIST_CONFIG.replace(
    'allowed_domains = ["example.com"]', 'allowed_domains = "example.com"'
)


def test_validate_flags_broken_relative_link(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("linked-rule", "See [the ghost](ghost.md) for details.\n")],
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "ghost.md" in out
    assert "does not exist" in out


def test_validate_allows_resolvable_relative_link(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[
            ("linking-rule", "See [style](style-rule.md).\n"),
            ("style-rule", "Style body\n"),
        ],
    )
    assert _validate.run(_ns(repo)) == 0


def test_validate_flags_disallowed_external_link(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(
        tmp_path,
        prompts=[("docs-prompt", {"body": "Read [docs](https://example.com/docs).\n"})],
    )
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "example.com" in out
    assert "allowed_domains" in out


def test_validate_allows_allowlisted_external_link(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(
        tmp_path,
        config_text=_ALLOWLIST_CONFIG,
        prompts=[("docs-prompt", {"body": "Read [docs](https://example.com/docs).\n"})],
    )
    assert _validate.run(_ns(repo)) == 0


def test_validate_ignores_link_alikes_in_code_fences(tmp_path, make_synthetic_repo):
    body = "Generics:\n\n```python\ndef first[T](items: list[T]) -> T | None:\n    ...\n```\n"
    repo = make_synthetic_repo(tmp_path, rules=[("generics-rule", body)])
    assert _validate.run(_ns(repo)) == 0


def test_validate_flags_link_escaping_artifact_root(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("escape-rule", "See [secret](../../secret.md).\n")],
    )
    (repo / "secret.md").write_text("outside the bundle\n", encoding="utf-8")
    rc = _validate.run(_ns(repo))
    assert rc == 1
    assert "escapes" in capsys.readouterr().out


def test_validate_flags_skill_reference_file_violation(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path)
    skill_dir = repo / "playbook" / "skills" / "demo"
    references = skill_dir / "references"
    references.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\nUse [notes](references/notes.md).\n",
        encoding="utf-8",
    )
    (references / "notes.md").write_text("Broken [ref](missing.md).\n", encoding="utf-8")
    rc = _validate.run(_ns(repo))
    assert rc == 1
    out = capsys.readouterr().out
    assert "missing.md" in out


def test_validate_flags_malformed_links_config(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, config_text=_BAD_LINKS_CONFIG)
    rc = _validate.run(_ns(repo))
    assert rc == 1
    assert "allowed_domains" in capsys.readouterr().out


class _InMemorySource(ArtifactSource):
    """Non-filesystem source: only the external-link policy can apply."""

    name = "in-memory"

    def __init__(self, prompts: list[Prompt]) -> None:
        self._prompts = prompts

    def list_rules(self) -> list[Rule]:
        return []

    def list_prompts(self) -> list[Prompt]:
        return self._prompts

    def list_skills(self) -> list[Skill]:
        return []

    def list_eval_tasks(self) -> list[EvalTask]:
        return []


def _prompt(body: str) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(id="p", name="P", description="d", slash="p"),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="in-memory",
    )


def test_non_filesystem_source_still_applies_external_policy(tmp_path):
    source = _InMemorySource([_prompt("Bad [x](https://example.com/x).\n")])
    errors = _validate_links.check_markdown_links(source, tmp_path, LinksConfig())
    assert len(errors) == 1
    assert "example.com" in errors[0].message


def test_non_filesystem_source_skips_relative_targets(tmp_path):
    source = _InMemorySource([_prompt("Rel [x](unresolvable.md).\n")])
    assert _validate_links.check_markdown_links(source, tmp_path, LinksConfig()) == []


def test_shipped_engine_artifacts_have_self_contained_links(tmp_path):
    """The CI gate: every markdown link in every shipped engine artifact must
    be self-contained under the strict default (empty allowlist)."""
    source = FileSystemArtifactSource(repo_root=tmp_path)
    errors = _validate_links.check_markdown_links(source, tmp_path, LinksConfig())
    assert errors == [], "\n".join(f"{e.path}: {e.message}" for e in errors)


def test_superpowers_pack_has_self_contained_links(tmp_path: Path) -> None:
    """The same CI gate over the opt-in superpowers pack (SPEC §11.5): it is
    walked only when enabled, so the engine-only gate above never sees it."""
    # The validator silently skips a package whose skills/ does not resolve, so
    # pin that it resolves to the shipped tree: otherwise this gate is vacuous.
    walked = _resource_subdir(PACK_NAME, "skills")
    assert walked is not None
    assert walked.resolve() == SKILLS_ROOT.resolve()
    assert any(walked.glob("*/SKILL.md"))
    source = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[PACK_NAME])
    errors = _validate_links.check_markdown_links(source, tmp_path, LinksConfig())
    assert errors == [], "\n".join(f"{e.path}: {e.message}" for e in errors)
