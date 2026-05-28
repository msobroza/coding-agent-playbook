"""Tests for the cap / coding-agent-playbook CLI dispatcher (PR 10)."""

from __future__ import annotations

import pytest

from coding_agent_playbook import __version__
from coding_agent_playbook.cli import build_parser, main


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

    args2 = parser.parse_args(["eval", "--show", "task-x"])
    assert args2.show == "task-x"


def test_eval_subparser_accepts_bare_id():
    parser = build_parser()
    args = parser.parse_args(["eval", "task-y"])
    assert args.id == "task-y"


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
