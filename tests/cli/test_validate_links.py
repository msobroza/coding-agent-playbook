"""Tests for the SPEC §12.6 self-contained-markdown-links rule (PR L).

Drives ``playbook validate`` end-to-end on synthetic consumer repos, plus the
CI gates asserting every *shipped* artifact, the engine's and every bundled
plugin's, is itself clean — those tests running under ``pytest -q`` are what
enforce the invariant on CI.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.catalog.roots import bundled_plugins
from coding_agent_playbook.catalog.source import ArtifactSource, FileSystemArtifactSource
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.config.tables.links import LinksConfig
from coding_agent_playbook.validation import _links as _validate_links
from tests._catalog import PLUGINS_ROOT, bundled_plugin_dirs
from tests.engine_version import ENGINE_VERSION

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.validation.findings import ValidationError

pytestmark = pytest.mark.catalog


def _ns(repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo))


_ALLOWLIST_CONFIG = f"""\
schema_version = 1
adapters_enabled = ["continue", "claude_code", "opencode"]
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "{ENGINE_VERSION}"

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

    def list_eval_samples(self) -> list[EvalSample]:
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


def _check_links_recording_visits(
    source: FileSystemArtifactSource, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[ValidationError], list[Path]]:
    """Run the link gate; return its errors and every markdown file it scanned.

    The gate silently skips a root that does not resolve, so only the visits
    prove it is not vacuous. Example::

        errors, visited = _check_links_recording_visits(source, tmp_path, monkeypatch)
    """
    visited: list[Path] = []
    real_scan = _validate_links._scan_markdown_file

    def _recording_scan(
        md: Path, *, root_dir: Path, links_config: LinksConfig
    ) -> list[ValidationError]:
        visited.append(md)
        return real_scan(md, root_dir=root_dir, links_config=links_config)

    monkeypatch.setattr(_validate_links, "_scan_markdown_file", _recording_scan)
    return _validate_links.check_markdown_links(source, repo, LinksConfig()), visited


def test_shipped_engine_artifacts_have_self_contained_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CI gate: every markdown link in every shipped engine artifact must
    be self-contained under the strict default (empty allowlist)."""
    source = FileSystemArtifactSource(repo_root=tmp_path)
    errors, visited = _check_links_recording_visits(source, tmp_path, monkeypatch)
    for kind in ("rules", "hooks"):
        assert any(kind in md.parts for md in visited), (
            f"the link gate visited no {kind[:-1]} of {source.engine_package} "
            f"({len(visited)} files scanned)"
        )
    assert errors == [], "\n".join(f"{e.path}: {e.message}" for e in errors)


def _plugins_with_link_checked_markdown() -> set[str]:
    """Names of the plugin dirs holding a ``.md``/``.md.j2`` file the link gate reads.

    Read from the checkout, not from the code under test, so a plugin the gate
    fails to walk shows up as missing. Example::

        _plugins_with_link_checked_markdown()  # {'mattpocock_skills', 'superpowers'}
    """
    kind_dirs = [
        (plugin_dir.name, plugin_dir / kind)
        for plugin_dir in bundled_plugin_dirs()
        for kind in _validate_links._LINK_CHECKED_SUBDIRS
    ]
    return {
        name
        for name, kind_dir in kind_dirs
        if kind_dir.is_dir()
        and any(path.name.endswith((".md", ".md.j2")) for path in kind_dir.rglob("*"))
    }


def test_every_bundled_plugin_has_self_contained_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same CI gate with every bundled plugin enabled (SPEC §11.5).

    Plugins are walked only when enabled, so the engine-only gate above never
    sees them. The plugin set is discovered, so a new ``catalog/plugins/<name>/``
    is gated with no edit here (acceptance 5). Each plugin's containment root is
    its own directory, so a link into ``core/`` or another plugin fails.
    """
    plugins = bundled_plugins()
    source = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=plugins)
    errors, visited = _check_links_recording_visits(source, tmp_path, monkeypatch)
    # The gate silently skips a plugin whose kind dirs do not resolve, so pin
    # that it walked every one that ships markdown: otherwise it is vacuous.
    plugins_root = PLUGINS_ROOT.resolve()
    walked = {
        md.resolve().relative_to(plugins_root).parts[0]
        for md in visited
        if md.resolve().is_relative_to(plugins_root)
    }
    assert walked == _plugins_with_link_checked_markdown(), (
        f"the link gate walked {sorted(walked)} of the bundled plugins {plugins}"
    )
    assert errors == [], "\n".join(f"{e.path}: {e.message}" for e in errors)
