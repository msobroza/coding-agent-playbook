"""``playbook docs-check``: the documentation guard twin (specs/prU-core-python-skills.md D69).

The stdlib checks (relative links, Python code blocks) run in-process on files
written under a temporary repository. The repo's own tools run through a
``FakeProc``: ``programs`` is what is installed, and an unscripted call fails
the test, so a row that expects no tool proves none was started.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands.twins import docs_check
from coding_agent_playbook.hook_runtime.git.parse import DiffLines
from tests.hook_runtime.fakes import FakeGit, FakeProc

#: Every tool docs-check may start, installed: a row only scripts the ones it expects.
EVERY_TOOL: Final = {
    name: f"/opt/bin/{name}"
    for name in ("mkdocs", "sphinx-build", "pytest", "markdownlint", "doc8")
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    built = Path(os.path.realpath(tmp_path)) / "consumer"
    (built / "docs").mkdir(parents=True)
    (built / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    return built


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _check(root: Path, *paths: str) -> int:
    return main(["docs-check", *paths, "--repo-root", str(root)])


def test_broken_relative_link_fails_with_file_and_line(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        root, "README.md", "# Title\n\nSee [guide](docs/guide.md).\nAnd [gone](docs/gone.md#x).\n"
    )

    assert _check(root, "README.md") == 1

    out = capsys.readouterr().out.splitlines()
    assert "README.md:4: broken relative link 'docs/gone.md#x' (no such file)" in out
    assert not any("docs/guide.md" in line for line in out)


def test_python_block_that_does_not_parse_fails_and_sessions_are_skipped(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        root,
        "docs/guide.md",
        "# Guide\n\n```python\nx = 1\ndef broken(:\n```\n\n"
        "```pycon\n>>> def also(:\n```\n\n```py\n>>> 1 +\n```\n\n"
        "`[not a link](missing.md)`\n",
    )

    assert _check(root, "docs/guide.md") == 1

    assert capsys.readouterr().out.splitlines() == [
        "docs/guide.md:5: Python code block does not parse: invalid syntax",
        "docs-check: 1 finding(s) in 1 file(s)",
    ]


def _run(root: Path, proc: FakeProc, *paths: str) -> int:
    args = build_parser().parse_args(["docs-check", *paths, "--repo-root", str(root)])
    return docs_check.run(args, proc=proc)


def test_repo_without_docs_tools_runs_only_the_stdlib_checks(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proc = FakeProc(programs=dict(EVERY_TOOL))
    _write(root, "notes.rst", "Notes\n=====\n")

    assert _run(root, proc, "docs/guide.md", "notes.rst") == 0

    assert proc.calls == []
    assert capsys.readouterr().out.splitlines() == ["docs-check: 2 file(s) clean"]


@pytest.mark.parametrize("config", ["mkdocs.yml", "mkdocs.yaml"])
def test_mkdocs_builds_strict_where_its_config_exists(
    config: str, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, config, "site_name: x\n")
    proc = FakeProc(programs=dict(EVERY_TOOL))
    proc.script(["mkdocs", "build"], returncode=1, stderr=b"WARNING - a link to 'gone.md'\n")

    assert _run(root, proc, "docs/guide.md") == 1

    (call,) = proc.calls
    assert call.argv[:3] == ("/opt/bin/mkdocs", "build", "--strict")
    assert call.argv[3:5] == ("--config-file", config)
    assert call.cwd == str(root)
    out = capsys.readouterr().out.splitlines()
    assert "docs-check: `mkdocs build --strict` failed (exit 1)" in out
    assert "  WARNING - a link to 'gone.md'" in out


@pytest.mark.parametrize("conf", ["docs/conf.py", "docs/source/conf.py", "doc/conf.py"])
def test_sphinx_builds_with_warnings_as_errors_where_conf_py_exists(
    conf: str, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, conf, "project = 'x'\n")
    proc = FakeProc(programs=dict(EVERY_TOOL))
    proc.script(["sphinx-build"])

    assert _run(root, proc, "docs/guide.md") == 0

    (call,) = proc.calls
    source = conf.rsplit("/", 1)[0]
    assert call.argv[:6] == ("/opt/bin/sphinx-build", "-W", "--keep-going", "-q", "-b", "html")
    assert call.argv[6] == source
    assert capsys.readouterr().out.splitlines()[-1] == "docs-check: 1 file(s) clean"


def test_missing_tool_fails_open_with_an_install_hint(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, "mkdocs.yml", "site_name: x\n")

    assert _run(root, FakeProc(), "docs/guide.md") == 0

    assert capsys.readouterr().out.splitlines() == [
        "docs-check: skipped `mkdocs build --strict`: mkdocs is not installed "
        "(install it: uv add --group docs mkdocs)",
        "docs-check: 1 file(s) clean",
    ]


@pytest.mark.parametrize(
    ("pyproject", "hint"),
    [
        ('[dependency-groups]\ndocs = ["mkdocs"]\n', "uv sync --group docs"),
        ('[project.optional-dependencies]\ndocs = ["mkdocs"]\n', "uv sync --extra docs"),
    ],
)
def test_a_docs_dependency_group_is_the_docs_toolchain_the_hint_names(
    pyproject: str, hint: str, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, "mkdocs.yml", "site_name: x\n")
    _write(root, "pyproject.toml", pyproject)

    assert _run(root, FakeProc(), "docs/guide.md") == 0

    assert f"(install it: {hint})" in capsys.readouterr().out


def test_doctests_run_on_the_changed_files_the_pytest_config_collects(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, "pyproject.toml", '[tool.pytest.ini_options]\naddopts = "--doctest-glob=*.md"\n')
    _write(root, "notes.rst", "Notes\n=====\n")
    proc = FakeProc(programs=dict(EVERY_TOOL))
    proc.script(["pytest"])

    assert _run(root, proc, "docs/guide.md", "notes.rst") == 0

    (call,) = proc.calls
    assert call.argv == ("/opt/bin/pytest", "docs/guide.md")


@pytest.mark.parametrize(
    ("config", "program", "changed"),
    [
        (".markdownlint.yaml", "markdownlint", "docs/guide.md"),
        (".doc8.ini", "doc8", "notes.rst"),
    ],
)
def test_linters_run_only_where_their_config_exists(
    config: str, program: str, changed: str, root: Path
) -> None:
    _write(root, config, "")
    _write(root, "notes.rst", "Notes\n=====\n")
    proc = FakeProc(programs=dict(EVERY_TOOL))
    proc.script([program])

    assert _run(root, proc, "docs/guide.md", "notes.rst") == 0

    (call,) = proc.calls
    assert call.argv == (f"/opt/bin/{program}", changed)


@pytest.mark.parametrize(("mode", "code"), [("warn", 0), ("block", 1)])
def test_guardrails_docs_mode_warn_reports_without_failing(
    mode: str, code: int, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, ".coding-agent-playbook.toml", f'[guardrails.docs]\nmode = "{mode}"\n')
    _write(root, "README.md", "[gone](gone.md)\n")

    assert _check(root, "README.md") == code

    assert "README.md:1: broken relative link 'gone.md' (no such file)" in capsys.readouterr().out


def test_guardrails_docs_mode_off_checks_nothing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, ".coding-agent-playbook.toml", '[guardrails.docs]\nmode = "off"\n')
    _write(root, "README.md", "[gone](gone.md)\n")
    _write(root, "mkdocs.yml", "site_name: x\n")

    assert _run(root, FakeProc(programs=dict(EVERY_TOOL)), "README.md") == 0

    assert capsys.readouterr().out.splitlines() == [
        'docs-check: off ([guardrails.docs] mode = "off")'
    ]


def test_a_named_path_that_does_not_exist_exits_2(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _check(root, "docs/nope.md") == 2

    assert capsys.readouterr().err.strip() == "error: no such file: docs/nope.md"


def _run_since_base(root: Path, proc: FakeProc, git: FakeGit) -> int:
    args = build_parser().parse_args(["docs-check", "--base", "B", "--repo-root", str(root)])
    return docs_check.run(args, proc=proc, git=git)


def test_without_paths_only_python_changes_since_the_base_check_nothing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, "mkdocs.yml", "site_name: x\n")
    _write(root, "src/a.py", "x = 1\n")
    git = FakeGit(
        merge_bases={("B", "HEAD"): "base"},
        worktree_diffs={"base": DiffLines(paths=("src/a.py",))},
    )

    assert _run_since_base(root, FakeProc(programs=dict(EVERY_TOOL)), git) == 0

    assert capsys.readouterr().out.splitlines() == ["docs-check: no documentation changed"]


def test_without_paths_the_docs_changed_since_the_base_are_checked(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, "README.md", "[gone](gone.md)\n")
    git = FakeGit(
        merge_bases={("B", "HEAD"): "base"},
        worktree_diffs={"base": DiffLines(paths=("src/a.py", "README.md", "docs/deleted.md"))},
        untracked=("docs/guide.md",),
    )

    assert _run_since_base(root, FakeProc(), git) == 1

    out = capsys.readouterr().out.splitlines()
    assert out[0] == "README.md:1: broken relative link 'gone.md' (no such file)"
    assert out[-1] == "docs-check: 1 finding(s) in 2 file(s)"


@pytest.mark.parametrize(
    ("path", "is_docs"),
    [
        ("README.md", True),
        ("docs/api/index.rst", True),
        ("docs/conf.py", True),
        ("docs/source/conf.py", True),
        ("doc/conf.py", True),
        ("mkdocs.yml", True),
        ("mkdocs.yaml", True),
        ("src/pkg/module.py", False),
        ("tests/test_a.py", False),
        ("pyproject.toml", False),
    ],
)
def test_docs_paths_is_the_d69_path_list(path: str, is_docs: bool) -> None:
    assert (docs_check.docs_paths([path]) == [path]) is is_docs


def test_a_tool_that_cannot_run_is_a_failure(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, "mkdocs.yml", "site_name: x\n")
    proc = FakeProc(programs=dict(EVERY_TOOL))
    proc.script(["mkdocs", "build"], timeout=True)

    assert _run(root, proc, "docs/guide.md") == 1

    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("docs-check: `mkdocs build --strict` failed: ")
    assert out[-1] == "docs-check: 1 finding(s) in 1 file(s)"


def test_a_failing_tool_prints_only_the_last_20_output_lines(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(root, "mkdocs.yml", "site_name: x\n")
    proc = FakeProc(programs=dict(EVERY_TOOL))
    output = "".join(f"line {n}\n" for n in range(1, 31)).encode()
    proc.script(["mkdocs", "build"], returncode=1, stdout=output)

    assert _run(root, proc, "docs/guide.md") == 1

    out = capsys.readouterr().out.splitlines()
    assert out[1:-1] == [f"  line {n}" for n in range(11, 31)]
