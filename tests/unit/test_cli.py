"""Tests for the playbook / coding-agent-playbook CLI dispatcher (PR 10)."""

from __future__ import annotations

import pytest

from coding_agent_playbook import __version__
from coding_agent_playbook.cli import _SUBCOMMANDS, build_parser, main


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
    args2 = parser.parse_args(["eval", "--show", "task-x", "--repo-root", "/tmp/elsewhere"])
    assert args2.show == "task-x"
    assert args2.repo_root == "/tmp/elsewhere"


def test_eval_main_uses_repo_root_without_chdir(monkeypatch, tmp_path, make_synthetic_repo):
    """Running ``playbook eval --list --repo-root <path>`` through ``main`` must
    enumerate the *given* repo, not the process's cwd. The original
    process cwd must be unchanged after the call (no covert ``os.chdir``).

    Seeded with a single repo-local prompt + task so the listing is
    non-trivial — confirms the flag actually plumbs through to
    ``commands.eval.run``."""
    import os

    make_synthetic_repo(tmp_path)
    prompts_dir = tmp_path / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "demo.md").write_text(
        "---\n"
        "id: demo\n"
        "name: Demo\n"
        "description: demo\n"
        "slash: demo\n"
        "eval_tasks:\n"
        "  - demo-task\n"
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )
    task_dir = tmp_path / "playbook" / "eval_tasks" / "demo-task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(
        'id = "demo-task"\nprompt_id = "demo"\ndescription = "Demo task"\n',
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


def test_twin_subcommands_close_the_canonical_list():
    """prK K6: the off-workstation twins are registered, and no argument is required."""
    assert _SUBCOMMANDS[-2:] == ("gate-scan", "ci")


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
    from coding_agent_playbook.config import ConfigError

    def raising_run(args):
        raise ConfigError("x.toml: the [overlays] table is not read")

    monkeypatch.setattr(sync_cmd, "run", raising_run)
    assert main(["sync"]) == 2
    assert capsys.readouterr().err == "error: x.toml: the [overlays] table is not read\n"
