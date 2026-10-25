"""``scripts/build_docs.py``: the one strict docs build, for people and for CI.

The process runner and the server are named fakes, so the tests need no Sphinx
and never start a build or a server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from build_docs import DEFAULT_PORT, INSTALL_HINT, DocsLayout, main, sphinx_command
from tests._catalog import REPO_ROOT

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class FakeRunner:
    """Records each command and answers with ``exit_code``."""

    exit_code: int = 0
    commands: list[list[str]] = field(default_factory=list)
    saw_build_dir: list[bool] = field(default_factory=list)
    build_dir: Path | None = None

    def __call__(self, command: list[str]) -> int:
        self.commands.append(command)
        if self.build_dir is not None:
            self.saw_build_dir.append(self.build_dir.exists())
        return self.exit_code


@dataclass
class FakeServer:
    """Records each ``(directory, port)`` it was asked to serve."""

    calls: list[tuple[Path, int]] = field(default_factory=list)

    def __call__(self, directory: Path, port: int) -> None:
        self.calls.append((directory, port))


def _layout(tmp_path: Path) -> DocsLayout:
    return DocsLayout(source_dir=tmp_path / "docs", build_dir=tmp_path / "docs" / "_build")


def test_builds_strictly_once_and_returns_sphinx_exit_code(tmp_path: Path) -> None:
    layout, runner, server = _layout(tmp_path), FakeRunner(), FakeServer()

    code = main([], layout=layout, run=runner, serve=server, has_sphinx=lambda: True)

    assert code == 0
    assert runner.commands == [sphinx_command(layout)]
    assert runner.commands[0][3:5] == ["-W", "--keep-going"]
    assert runner.commands[0][-2:] == [str(layout.source_dir), str(layout.html_dir)]
    assert server.calls == []


def test_a_failed_build_returns_its_code_and_is_never_served(tmp_path: Path) -> None:
    runner, server = FakeRunner(exit_code=1), FakeServer()

    code = main(
        ["--serve"], layout=_layout(tmp_path), run=runner, serve=server, has_sphinx=lambda: True
    )

    assert code == 1
    assert server.calls == []


@pytest.mark.parametrize(
    ("argv", "port"), [(["--serve"], DEFAULT_PORT), (["--serve", "9001"], 9001)]
)
def test_serve_previews_the_built_site(tmp_path: Path, argv: list[str], port: int) -> None:
    layout, server = _layout(tmp_path), FakeServer()

    main(argv, layout=layout, run=FakeRunner(), serve=server, has_sphinx=lambda: True)

    assert server.calls == [(layout.html_dir, port)]


def test_clean_deletes_the_old_build_before_building(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    (layout.html_dir).mkdir(parents=True)
    (layout.html_dir / "stale.html").write_text("old")
    runner = FakeRunner(build_dir=layout.build_dir)

    main(["--clean"], layout=layout, run=runner, has_sphinx=lambda: True)

    assert runner.saw_build_dir == [False]


def test_without_sphinx_it_names_the_fix_and_builds_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner()

    code = main([], layout=_layout(tmp_path), run=runner, has_sphinx=lambda: False)

    assert code == 2
    assert runner.commands == []
    assert INSTALL_HINT in capsys.readouterr().err


def test_the_repo_layout_points_at_the_sphinx_sources() -> None:
    layout = DocsLayout.of_repo(REPO_ROOT)

    assert (layout.source_dir / "conf.py").is_file()
    assert layout.html_dir == REPO_ROOT / "docs" / "_build" / "html"


def test_the_docs_workflow_builds_through_the_script() -> None:
    # One build command: CI must not drift from what contributors run.
    workflow = (REPO_ROOT / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")

    assert "python scripts/build_docs.py" in workflow
    assert "sphinx-build" not in workflow
