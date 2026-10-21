"""``preview_layout_rewrites``: validate's layout report from a scratch render (D71; prU L0-23)."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.rendering.jinja import TemplateSecurityError
from coding_agent_playbook.sync import _check_modes, layout_preview
from coding_agent_playbook.sync.layout_preview import LayoutPreviewError, preview_layout_rewrites
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.usefixtures("hermetic_git_env"), pytest.mark.catalog]

_CONFIG = ".coding-agent-playbook.toml"


def _repo(repo: Path, layout: str = "") -> SyncContext:
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "probe"\nrequires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(
        repo_root=str(repo),
        non_interactive=True,
        name="probe",
        kind="python-library",
        adapters="agents_md",
        framework="mattpocock",
    )
    assert _init.run(args) == 0
    if layout:
        config = repo / _CONFIG
        config.write_text(
            config.read_text(encoding="utf-8") + f"\n[layout]\n{layout}\n", encoding="utf-8"
        )
    return SyncContext.from_repo(repo)


def _no_render(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("the default layout must not render anything")


def test_the_default_layout_reports_nothing_without_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _repo(tmp_path)
    monkeypatch.setattr(layout_preview, "_rendered_scratch", _no_render)

    assert preview_layout_rewrites(ctx) == []


def test_reports_the_rewrites_of_the_rendered_files_without_writing_the_repo(
    tmp_path: Path,
) -> None:
    ctx = _repo(tmp_path, 'agents = "notes/agents"')
    before = (tmp_path / "AGENTS.md").read_bytes()

    rewrites = preview_layout_rewrites(ctx)

    assert "AGENTS.md" in {rewrite.path for rewrite in rewrites}
    assert (tmp_path / "AGENTS.md").read_bytes() == before


def test_a_failed_render_is_a_layout_preview_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _repo(tmp_path, 'specs = "specs"')

    def _rejected(*_args: object, **_kwargs: object) -> None:
        raise TemplateSecurityError("rules/x.md", "access to attribute '__class__' denied")

    monkeypatch.setattr(_check_modes, "_render_into", _rejected)

    with pytest.raises(LayoutPreviewError, match=r"rendering the sync output failed: rules/x\.md"):
        preview_layout_rewrites(ctx)
