"""Tests for the playbook / coding-agent-playbook CLI dispatcher (PR 10)."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook import __version__
from coding_agent_playbook.catalog import roots as catalog
from coding_agent_playbook.cli import main
from coding_agent_playbook.cli.parser import _COMMANDS, _SUBCOMMANDS, build_parser

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable


def break_catalog(monkeypatch: pytest.MonkeyPatch, root: Path) -> str:
    """Point the engine at an empty ``<root>/src/coding_agent_playbook``.

    Neither catalog home exists then, as in a wheel whose catalog mapping was
    lost. Returns the exact stderr ``main`` must print: the packaged candidate
    first, then the checkout one (the spec's missing-catalog error line).

    Example::

        expected = break_catalog(monkeypatch, tmp_path)
    """
    package_dir = root / "src" / "coding_agent_playbook"
    package_dir.mkdir(parents=True)
    monkeypatch.setattr(catalog, "_PACKAGE_DIR", package_dir)
    return (
        "error: the engine's catalog was not found "
        f"(looked in {package_dir / '_catalog'}, {root / 'catalog'}); "
        "reinstall coding-agent-playbook\n"
    )


def test_version_flag_prints_name_and_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "coding-agent-playbook" in out
    assert __version__ in out


def test_no_args_prints_help_and_exits_zero(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("name", _SUBCOMMANDS)
def test_every_subcommand_in_module_tuple_is_registered(name):
    """Every name in :data:`_SUBCOMMANDS` resolves to an argparse subparser
    with a default ``func``. Keeps the canonical list and the actual
    parser surface in sync.
    """
    parser = build_parser()
    args = parser.parse_args([name] if name != "render" else [name, "any-id"])
    assert args.command == name
    assert callable(getattr(args, "func", None))


def test_every_subcommand_is_a_command_in_help_order() -> None:
    """Every subcommand is a Command module (CP-3 emptied the legacy table), and
    ``_SUBCOMMANDS`` is their names in the order ``playbook --help`` has always listed."""
    help_order = (
        "init",
        "sync",
        "check",
        "validate",
        "render",
        "eval",
        "metrics",
        "import-harness",
        "validate-harness",
        "forge",
        "gate-scan",
        "ci",
        "scan-sinks",
        "check-notebooks",
        "scan-secrets",
        "check-commit-trailers",
        "check-deps",
        "docs-check",
    )

    assert tuple(command.NAME for command in _COMMANDS) == help_order
    assert help_order == _SUBCOMMANDS


def test_command_names_are_unique_and_match_their_place() -> None:
    """A Command is its module (no command object): its ``NAME`` is the module's name with
    dashes, and ``_COMMANDS`` lists the modules in ``playbook --help`` order."""
    command_names = [command.NAME for command in _COMMANDS]

    assert len(set(command_names)) == len(command_names)
    assert command_names == [name for name in _SUBCOMMANDS if name in command_names]
    for command in _COMMANDS:
        assert isinstance(command, ModuleType)
        assert command.__name__.rsplit(".", 1)[-1].replace("_", "-") == command.NAME


def test_main_dispatches_to_a_command_run_patched_after_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``build_parser`` reads a Command's ``run`` on each call, so a patched ``run`` bites."""
    from coding_agent_playbook.commands import check as check_cmd

    seen: list[str | None] = []

    def fake_run(args: argparse.Namespace) -> int:
        seen.append(args.repo_root)
        return 5

    monkeypatch.setattr(check_cmd, "run", fake_run)
    assert main(["check", "--repo-root", "/r"]) == 5
    assert seen == ["/r"]


def test_sync_subparser_accepts_check_and_repo_root_flags():
    parser = build_parser()
    args = parser.parse_args(["sync", "--check", "--repo-root", "/tmp/whatever"])
    assert args.command == "sync"
    assert args.check is True
    assert args.repo_root == "/tmp/whatever"


def test_init_subparser_accepts_all_flags():
    parser = build_parser()
    args = parser.parse_args(
        [
            "init",
            "--non-interactive",
            "--name",
            "x",
            "--kind",
            "python-library",
            "--description",
            "d",
            "--adapters",
            "continue,claude_code",
            "--overlays",
            "overlay-a",
        ]
    )
    assert args.command == "init"
    assert args.non_interactive is True
    assert args.name == "x"
    assert args.kind == "python-library"
    assert args.adapters == "continue,claude_code"
    assert args.overlays == "overlay-a"


def test_check_subparser_accepts_refresh():
    parser = build_parser()
    args = parser.parse_args(["check", "--refresh"])
    assert args.command == "check"
    assert args.refresh is True


def test_validate_subparser_accepts_repo_root():
    parser = build_parser()
    args = parser.parse_args(["validate", "--repo-root", "/tmp/x"])
    assert args.command == "validate"
    assert args.repo_root == "/tmp/x"


def test_render_subparser_requires_id_and_accepts_flags():
    parser = build_parser()
    args = parser.parse_args(["render", "my-rule", "--format", "continue", "--show-source"])
    assert args.command == "render"
    assert args.id == "my-rule"
    assert args.format == "continue"
    assert args.show_source is True


def test_render_subparser_show_rules_flag():
    parser = build_parser()
    args = parser.parse_args(["render", "p", "--show-rules"])
    assert args.show_rules is True


def test_eval_subparser_accepts_list_and_show():
    parser = build_parser()
    args = parser.parse_args(["eval", "--list"])
    assert args.command == "eval"
    assert args.list is True

    args2 = parser.parse_args(["eval", "--show", "sample-x"])
    assert args2.show == "sample-x"


def test_eval_subparser_accepts_bare_id():
    parser = build_parser()
    args = parser.parse_args(["eval", "sample-y"])
    assert args.id == "sample-y"


def test_eval_subparser_accepts_repo_root():
    """``playbook eval`` must accept ``--repo-root <path>`` for parity with every
    other subcommand (sync/check/validate/render). Without it, tests and
    non-cwd invocations would have to ``os.chdir`` into the target repo —
    fragile and surprising next to the other subcommands."""
    parser = build_parser()
    args = parser.parse_args(["eval", "--list", "--repo-root", "/tmp/somewhere"])
    assert args.command == "eval"
    assert args.list is True
    assert args.repo_root == "/tmp/somewhere"

    # Combined with --show.
    args2 = parser.parse_args(["eval", "--show", "sample-x", "--repo-root", "/tmp/elsewhere"])
    assert args2.show == "sample-x"
    assert args2.repo_root == "/tmp/elsewhere"


def test_eval_main_uses_repo_root_without_chdir(monkeypatch, tmp_path, make_synthetic_repo):
    """Running ``playbook eval --list --repo-root <path>`` through ``main`` must
    enumerate the *given* repo, not the process's cwd. The original
    process cwd must be unchanged after the call (no covert ``os.chdir``).

    Seeded with a single repo-local prompt + sample so the listing is
    non-trivial — confirms the flag actually plumbs through to
    ``commands.eval.run``."""
    import os

    make_synthetic_repo(tmp_path)
    prompts_dir = tmp_path / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "demo.md").write_text(
        "---\nid: demo\nname: Demo\ndescription: demo\nslash: demo\n---\nBody.\n",
        encoding="utf-8",
    )
    sample_dir = tmp_path / "playbook" / "eval_samples" / "demo" / "demo-sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "sample.toml").write_text(
        'id = "demo/demo-sample"\ndescription = "Demo sample"\n',
        encoding="utf-8",
    )

    # Pin cwd to a unrelated dir; the command must NOT silently chdir into
    # tmp_path.
    cwd_before = os.getcwd()
    rc = main(["eval", "--list", "--repo-root", str(tmp_path)])
    assert rc == 0
    assert os.getcwd() == cwd_before


def test_metrics_subparser_accepts_paths_and_flags():
    parser = build_parser()
    args = parser.parse_args(
        [
            "metrics",
            "a.py",
            "b.py",
            "--baseline",
            "git:HEAD",
            "--mode",
            "absolute",
            "--strict",
            "--format",
            "json",
            "--repo-root",
            "/tmp/x",
        ]
    )
    assert args.command == "metrics"
    assert args.paths == ["a.py", "b.py"]
    assert args.baseline == "git:HEAD"
    assert args.mode == "absolute"
    assert args.strict is True
    assert args.format == "json"
    assert args.repo_root == "/tmp/x"


def test_metrics_subparser_defaults():
    parser = build_parser()
    args = parser.parse_args(["metrics"])
    assert args.command == "metrics"
    assert args.paths == []
    assert args.baseline is None
    assert args.mode is None
    assert args.strict is False
    assert args.format == "text"
    assert (args.select, args.extend_select, args.ignore) == (None, None, None)
    assert (args.changed, args.emit_measurements) == (False, None)


def test_metrics_subparser_new_flags():
    """prK §F.0.3 items 2-4: selection, --changed and the measurement snapshot."""
    args = build_parser().parse_args(
        [
            "metrics",
            "--select",
            "quality",
            "--extend-select",
            "ruff_violations,file_sloc",
            "--ignore",
            "lcom4",
            "--changed",
            "--emit-measurements",
            "cov.json",
            "--baseline",
            "json:base.json",
        ]
    )
    assert args.select == "quality"
    assert args.extend_select == "ruff_violations,file_sloc"
    assert args.ignore == "lcom4"
    assert args.changed is True
    assert args.emit_measurements == "cov.json"
    assert args.baseline == "json:base.json"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [([], None), (["--run-tests"], True), (["--no-run-tests"], False)],
)
def test_metrics_run_tests_is_tristate_default_none(argv, expected):
    """``None`` defers to ``[metrics] run_tests``; ``--no-run-tests`` overrides it (§F.0.3 item 6)."""
    assert build_parser().parse_args(["metrics", *argv]).run_tests is expected


def test_twin_subcommands_close_the_canonical_list():
    """prK K6-K8 and prU D69: the off-workstation twins are registered, no argument required."""
    assert _SUBCOMMANDS[-8:] == (
        "gate-scan",
        "ci",
        "scan-sinks",
        "check-notebooks",
        "scan-secrets",
        "check-commit-trailers",
        "check-deps",
        "docs-check",
    )


def test_check_deps_accepts_base():
    """prK §E.4: ``check-deps [--base REF]``; without one the default branch is the base."""
    parser = build_parser()
    default = parser.parse_args(["check-deps"])
    based = parser.parse_args(["check-deps", "--base", "origin/main", "--repo-root", "/r"])

    assert (default.command, default.base, default.repo_root) == ("check-deps", None, None)
    assert (based.base, based.repo_root) == ("origin/main", "/r")


def test_check_commit_trailers_accepts_msgfile_or_range():
    """prK §E.4: the commit-msg stage passes a file; CI passes --range (the command checks one)."""
    parser = build_parser()
    msgfile = parser.parse_args(["check-commit-trailers", ".git/COMMIT_EDITMSG"])
    ranged = parser.parse_args(["check-commit-trailers", "--range", "A..B", "--repo-root", "/r"])

    assert (msgfile.msgfile, msgfile.rev_range) == (".git/COMMIT_EDITMSG", None)
    assert (ranged.msgfile, ranged.rev_range, ranged.repo_root) == (None, "A..B", "/r")


def test_scan_secrets_modes_are_mutually_exclusive():
    """prK §E.4: one of --staged / --range / --worktree, or PATHS (checked by the command)."""
    parser = build_parser()
    staged = parser.parse_args(["scan-secrets", "--staged"])
    worktree = parser.parse_args(["scan-secrets", "--worktree", "--format", "json"])
    ranged = parser.parse_args(["scan-secrets", "--range", "A..B"])
    paths = parser.parse_args(["scan-secrets", "a.py", "b/.env"])

    assert (staged.staged, staged.worktree, staged.rev_range, staged.paths) == (
        True,
        False,
        None,
        [],
    )
    assert (worktree.worktree, worktree.format) == (True, "json")
    assert ranged.rev_range == "A..B"
    assert paths.paths == ["a.py", "b/.env"]
    for pair in (
        ["--staged", "--worktree"],
        ["--staged", "--range", "A..B"],
        ["--worktree", "--range", "A..B"],
    ):
        with pytest.raises(SystemExit):
            parser.parse_args(["scan-secrets", *pair])


def test_scan_sinks_subparser_accepts_staged_or_range():
    parser = build_parser()
    staged = parser.parse_args(["scan-sinks", "--staged", "--format", "json"])
    ranged = parser.parse_args(["scan-sinks", "--range", "A..B", "--repo-root", "/tmp/x"])
    defaults = parser.parse_args(["scan-sinks"])

    assert (staged.staged, staged.rev_range, staged.format) == (True, None, "json")
    assert (ranged.staged, ranged.rev_range, ranged.repo_root) == (False, "A..B", "/tmp/x")
    assert (defaults.staged, defaults.rev_range, defaults.format) == (False, None, "text")
    with pytest.raises(SystemExit):
        parser.parse_args(["scan-sinks", "--staged", "--range", "A..B"])


def test_check_notebooks_subparser_takes_paths():
    parser = build_parser()
    args = parser.parse_args(["check-notebooks", "a.ipynb", "nb/b.ipynb"])

    assert (args.command, args.paths) == ("check-notebooks", ["a.ipynb", "nb/b.ipynb"])
    assert parser.parse_args(["check-notebooks"]).paths == []


def test_gate_scan_subparser_accepts_range_and_format():
    parser = build_parser()
    args = parser.parse_args(
        ["gate-scan", "--range", "HEAD~1..HEAD", "--format", "json", "--repo-root", "/tmp/x"]
    )
    assert (args.command, args.rev_range, args.format, args.repo_root) == (
        "gate-scan",
        "HEAD~1..HEAD",
        "json",
        "/tmp/x",
    )
    defaults = parser.parse_args(["gate-scan"])
    assert (defaults.rev_range, defaults.format, defaults.repo_root) == (None, "text", None)


def test_ci_subparser_accepts_base_steps_format():
    parser = build_parser()
    args = parser.parse_args(
        ["ci", "--base", "origin/main", "--steps", "validate,gate-scan", "--format", "json"]
    )
    assert (args.command, args.base, args.steps, args.format) == (
        "ci",
        "origin/main",
        "validate,gate-scan",
        "json",
    )
    defaults = parser.parse_args(["ci"])
    assert (defaults.base, defaults.steps, defaults.format) == (None, None, "text")


def test_main_returns_func_exit_code(monkeypatch, tmp_path):
    """Plumb a fake subcommand and verify main forwards its return code."""
    from coding_agent_playbook.commands import sync as sync_cmd

    def fake_run(args):
        return 7

    # The CLI's argparse parser was already built with sync_cmd.run as the
    # subparser's func. Patching the module attribute is enough because
    # build_parser is re-called inside main() each invocation.
    monkeypatch.setattr(sync_cmd, "run", fake_run)
    assert main(["sync"]) == 7


def test_main_translates_missing_config_to_exit_2(tmp_path, capsys):
    """A missing .coding-agent-playbook.toml raises FileNotFoundError inside
    the sync command; main should translate that into a friendly error +
    exit 2."""
    assert main(["sync", "--repo-root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_main_translates_config_error_to_exit_2(monkeypatch, capsys):
    """A ConfigError (a config the engine would misread) is reported like a
    missing config: ``error: <message>`` on stderr, exit 2, no traceback."""
    from coding_agent_playbook.commands import sync as sync_cmd
    from coding_agent_playbook.config.schema import ConfigError

    def raising_run(args):
        raise ConfigError("x.toml: the [overlays] table is not read")

    monkeypatch.setattr(sync_cmd, "run", raising_run)
    assert main(["sync"]) == 2
    assert capsys.readouterr().err == "error: x.toml: the [overlays] table is not read\n"


def test_missing_precommit_template_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A broken install missing the pre-commit template exits 2 with no traceback."""
    from coding_agent_playbook.commands import init as init_cmd
    from coding_agent_playbook.precommit import PrecommitTemplateMissingError

    missing = Path("/broken/templates/precommit/config.yaml.j2")

    def raising_run(args: object) -> int:
        raise PrecommitTemplateMissingError(missing)

    monkeypatch.setattr(init_cmd, "run", raising_run)
    assert main(["init"]) == 2
    assert capsys.readouterr().err == (
        f"error: the engine's pre-commit template was not found at {missing}; "
        "reinstall coding-agent-playbook\n"
    )


def test_main_reports_any_exit_two_error_as_an_error_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``main`` maps the shared exit-2 base, so a command's error type needs no cli entry."""
    from coding_agent_playbook.commands import validate as validate_cmd
    from coding_agent_playbook.exit_two import ExitTwoError

    class FakeCommandError(ExitTwoError):
        """An error type ``cli`` has never heard of."""

    def raising_run(args: object) -> int:
        raise FakeCommandError("the widget is missing")

    monkeypatch.setattr(validate_cmd, "run", raising_run)
    assert main(["validate"]) == 2
    assert capsys.readouterr().err == "error: the widget is missing\n"


def test_sync_exits_2_when_catalog_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_synthetic_repo: Callable[..., Path],
) -> None:
    """A lookup miss used to render zero engine artifacts silently."""
    expected = break_catalog(monkeypatch, tmp_path)
    repo = make_synthetic_repo(tmp_path)

    assert main(["sync", "--repo-root", str(repo)]) == 2
    assert capsys.readouterr().err == expected


def test_eval_list_exits_2_when_catalog_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_synthetic_repo: Callable[..., Path],
) -> None:
    expected = break_catalog(monkeypatch, tmp_path)
    repo = make_synthetic_repo(tmp_path)

    assert main(["eval", "--list", "--repo-root", str(repo)]) == 2
    assert capsys.readouterr().err == expected
