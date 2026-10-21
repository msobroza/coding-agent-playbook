"""``playbook validate`` enforces the hook trust contract H1-H21 (specs/prK-lifecycle-hooks.md §B.5).

Validate builds its context with ``tolerate_load_errors=True`` (P8c), so every
malformed ``HOOK.md`` is a ``FAIL`` line rather than a traceback, next to the
per-hook rules (``classify_hook``), the refused layer overrides (H2, H14, H15),
the body checks (H19) and the rules across hooks and config
(``classify_hook_set``). Warnings (degraded cells, clamps) print to stderr and
pass. The pure rules are unit-tested in ``tests/hooks/contract/test_contract*.py``.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.validation import context as _validate_context
from tests.hook_runtime.handlers.pack_repo import engine_hook_paths

if TYPE_CHECKING:
    from collections.abc import Callable

    SyntheticRepoFactory = Callable[..., Path]
    HookFactory = Callable[..., Path]
    PackageFactory = Callable[..., str]

_CONFIG = """\
schema_version = 1
adapters_enabled = ["claude_code", "opencode"]
overlays_enabled = {overlays}

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"
{extra}"""

#: What ``screen_regex`` says about the classic catastrophic-backtracking shape (§E.4).
REDOS = (
    "regex '(a+)+$' nests unbounded quantifiers (like (a+)+), which can backtrack "
    "catastrophically; bound the inner or the outer repeat"
)

# The sample hooks bind builtins guard_x/guard_y/guard_z, which validate (H6)
# resolves through the handler registry: install them as a real entry point.
pytestmark = pytest.mark.usefixtures("sample_hook_handlers")


def _config(*, overlays: tuple[str, ...] = (), extra: str = "") -> str:
    listed = "[" + ", ".join(f'"{name}"' for name in overlays) + "]"
    return _CONFIG.format(overlays=listed, extra=extra)


def _run(repo: Path) -> int:
    return _validate.run(argparse.Namespace(repo_root=str(repo)))


def _fail_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("FAIL ")]


def _ok_count(out: str) -> int:
    line = next(line for line in out.splitlines() if line.startswith("OK "))
    return int(line.split()[1])


def _overlay_hooks(make_package: PackageFactory, name: str = "acme_hooks_k1") -> tuple[str, Path]:
    """An importable overlay package shipping ``resources/hooks/``; returns (name, hooks dir)."""
    make_package(name, resources=True)
    module_file = importlib.import_module(name).__file__
    assert module_file is not None
    hooks = Path(module_file).parent / "resources" / "hooks"
    hooks.mkdir()
    return name, hooks


def test_validate_counts_hooks_in_ok_line(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    assert _run(repo) == 0
    without_hooks = _ok_count(capsys.readouterr().out)
    make_hook(repo / "playbook" / "hooks", "guard-x")
    make_hook(repo / "playbook" / "hooks", "guard-y", category="verify")

    assert _run(repo) == 0

    assert _ok_count(capsys.readouterr().out) == without_hooks + 2


def test_malformed_hook_reports_fail_line_not_traceback(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    hooks = repo / "playbook" / "hooks"
    bad_type = make_hook(hooks, "guard-x", timeout="2s")
    contract_key = make_hook(hooks, "guard-y", handler={"builtin": "guard_y", "url": "http://x"})
    both = make_hook(hooks, "guard-z", marker="HOOK.md")
    make_hook(hooks, "guard-z", marker="HOOK.md.j2")

    assert _run(repo) == 1

    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    assert _fail_lines(captured.out) == [
        f"FAIL {bad_type}: timeout: expected a number of seconds, got '2s'",
        f"FAIL {contract_key}: handler.url: 'url': HTTP/async/rewrite handlers are not part of "
        "the hook contract (SPEC §17.1)",
        f"FAIL {both.parent}: layout: both HOOK.md and HOOK.md.j2 in one hook directory; "
        "keep exactly one",
    ]


def test_per_hook_rules_fail_and_warnings_pass(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    hooks = repo / "playbook" / "hooks"
    degraded = make_hook(
        hooks,
        "guard-x",
        events=["pre_tool_use", "subagent_stop"],
        supports=["claude_code", "opencode"],
    )
    assert _run(repo) == 0
    assert capsys.readouterr().err.splitlines() == [
        f"warning: {degraded}: event 'subagent_stop' is not supported by adapter 'opencode' "
        "(degraded)"
    ]

    strict = make_hook(hooks, "guard-y", on_error="deny", decisions=["deny", "allow"])

    assert _run(repo) == 1
    assert _fail_lines(capsys.readouterr().out) == [
        f"FAIL {strict}: decision 'allow' is never permitted: it would bypass the harness "
        "permission system",
        f"FAIL {strict}: on_error 'deny' (fail-closed) is reserved for overlay hooks",
    ]


def _h14(repo: Path, make_hook: HookFactory, make_package: PackageFactory) -> tuple[str, str]:
    name, hooks = _overlay_hooks(make_package)
    make_hook(hooks, "guard-x", decisions=["deny", "none"])
    second, second_hooks = _overlay_hooks(make_package, "acme_hooks_k1_b")
    path = make_hook(second_hooks, "guard-x", decisions=["none"])
    config = _config(overlays=(name, second))
    return config, f"FAIL {path}: overlay {second!r} override of 'guard-x' drops decision 'deny'"


def _h15_disable(
    repo: Path, make_hook: HookFactory, make_package: PackageFactory
) -> tuple[str, str]:
    name, hooks = _overlay_hooks(make_package)
    make_hook(hooks, "pii-guard", mandatory=True)
    config = _config(overlays=(name,), extra='\n[hooks]\nenabled = true\ndisable = ["pii-guard"]\n')
    message = f"[hooks] disable: 'pii-guard' is mandatory (overlay {name}) and cannot be disabled"
    return config, f"FAIL {repo / '.coding-agent-playbook.toml'}: {message}"


def _h15_off(repo: Path, make_hook: HookFactory, make_package: PackageFactory) -> tuple[str, str]:
    name, hooks = _overlay_hooks(make_package)
    make_hook(hooks, "pii-guard", mandatory=True)
    config = _config(overlays=(name,), extra="\n[hooks]\nenabled = false\n")
    message = (
        f"[hooks] enabled = false while overlay {name!r} ships mandatory hook 'pii-guard'; "
        "mandatory hooks cannot be switched off: set enabled = true"
    )
    return config, f"FAIL {repo / '.coding-agent-playbook.toml'}: {message}"


def _h16(repo: Path, make_hook: HookFactory, make_package: PackageFactory) -> tuple[str, str]:
    path = make_hook(
        repo / "playbook" / "hooks",
        "guard-x",
        scripts=True,
        handler={"command": "python", "script": "scripts/check.py"},
    )
    (path.parent / "scripts" / "check.py").write_text("print('ok')\n", encoding="utf-8")
    config = _config(extra="\n[hooks]\nenabled = true\n")
    return config, (
        f"FAIL {path}: hook 'guard-x' runs code from '<repo-local>'; "
        "add it to [hooks] allow_code_from"
    )


def _h20(repo: Path, make_hook: HookFactory, make_package: PackageFactory) -> tuple[str, str]:
    rule = repo / "playbook" / "rules" / "guardrail-x.md"
    rule.parent.mkdir(parents=True)
    rule.write_text(
        "---\nid: guardrail-x\nname: X\ndescription: d\nscope: always\n---\nBody\n",
        encoding="utf-8",
    )
    return _config(), f"FAIL {rule}: rule id 'guardrail-x' uses the reserved 'guardrail-' prefix"


def _h21(
    extra: str, message: str
) -> Callable[[Path, HookFactory, PackageFactory], tuple[str, str]]:
    def build(repo: Path, make_hook: HookFactory, make_package: PackageFactory) -> tuple[str, str]:
        make_hook(repo / "playbook" / "hooks", "guard-x")
        return _config(extra=extra), f"FAIL {repo / '.coding-agent-playbook.toml'}: {message}"

    return build


_SET_LEVEL: list[tuple[str, Callable[[Path, HookFactory, PackageFactory], tuple[str, str]]]] = [
    ("H14", _h14),
    ("H15-disable-mandatory", _h15_disable),
    ("H15-enabled-false", _h15_off),
    ("H16", _h16),
    ("H20", _h20),
    (
        "H21-unknown-id",
        _h21(
            '\n[hooks]\nenabled = true\ndisable = ["guard-y"]\n',
            "[hooks] disable: unknown hook id 'guard-y'; did you mean 'guard-x'?",
        ),
    ),
    (
        "H21-overlap",
        _h21(
            '\n[hooks]\nenabled = true\nenable = ["guard-x"]\ndisable = ["guard-x"]\n',
            "[hooks] enable and disable both name 'guard-x'; disable wins, so list it in one "
            "of them only",
        ),
    ),
    (
        "H21-allow-code-from",
        _h21(
            '\n[hooks]\nenabled = true\nallow_code_from = ["acme"]\n',
            "[hooks] allow_code_from: 'acme' is neither an enabled overlay nor '<repo-local>'; "
            "allowed: <repo-local>",
        ),
    ),
    (
        "H21-unknown-sub-table",
        _h21(
            '\n[hooks]\nenabled = true\n\n[hooks.guard-q]\nmode = "warn"\n',
            "[hooks.guard-q]: unknown hook id 'guard-q'; did you mean 'guard-x'?",
        ),
    ),
    (
        "H21-stages",
        _h21(
            '\n[hooks]\nenabled = true\n\n[hooks.stop-ci-parity-gate]\nstages = ["lint"]\n',
            "[hooks.stop-ci-parity-gate] stages: must be a list drawn from 'typecheck', "
            "'tests', got ['lint']",
        ),
    ),
    (
        "H21-redos-extra-pattern",
        _h21(
            "\n[hooks]\nenabled = true\n\n[hooks.secret-content-guard]\n"
            'extra_patterns = [{id = "x", regex = "(a+)+$"}]\n',
            f"[hooks.secret-content-guard] extra_patterns: {REDOS}",
        ),
    ),
    (
        "H21-cutover-date",
        _h21(
            "\n[hooks.commit_convention]\ncutover_date = 2026-10-15\n",
            '[hooks.commit_convention] cutover_date: must be a "YYYY-MM-DD" string (quoted: a '
            "TOML string, not a TOML date literal), got datetime.date(2026, 10, 15)",
        ),
    ),
]


@pytest.mark.parametrize("build", [case[1] for case in _SET_LEVEL], ids=[c[0] for c in _SET_LEVEL])
def test_set_level_rule(
    build: Callable[[Path, HookFactory, PackageFactory], tuple[str, str]],
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    make_package: PackageFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    config, expected = build(repo, make_hook, make_package)
    (repo / ".coding-agent-playbook.toml").write_text(config, encoding="utf-8")

    assert _run(repo) == 1

    assert expected in _fail_lines(capsys.readouterr().out)


def test_local_toml_hooks_table_is_validate_error(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    local = repo / ".coding-agent-playbook.local.toml"
    local.write_text("[hooks]\nenabled = false\n", encoding="utf-8")

    assert _run(repo) == 1

    assert _fail_lines(capsys.readouterr().out) == [
        f"FAIL {local}: hooks.enabled: [hooks] and [guardrails] are read from the committed "
        "config only, so these local values are ignored; move them to the committed config "
        "or delete them"
    ]


def test_hook_body_links_are_checked(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    path = make_hook(repo / "playbook" / "hooks", "guard-x", body="See [x](../../../../x.md).\n")

    assert _run(repo) == 1

    (line,) = _fail_lines(capsys.readouterr().out)
    assert line.startswith(f"FAIL {path}: markdown link '../../../../x.md' (line ")
    assert "escapes the artifact root" in line


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            '{{ rule("python-style") }}\n',
            "body calls {{ rule(...) }} — hook bodies cannot include rules",
        ),
        ("{% if x %}unclosed\n", "Jinja syntax error: Unexpected end of template."),
    ],
    ids=["rule-call", "syntax"],
)
def test_hook_j2_body_is_checked(
    body: str,
    expected: str,
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    path = make_hook(repo / "playbook" / "hooks", "guard-x", marker="HOOK.md.j2", body=body)

    assert _run(repo) == 1

    assert f"FAIL {path}: {expected}" in _fail_lines(capsys.readouterr().out)[0]


def test_validate_without_config_checks_hooks_and_names_the_skipped_policy_rules(
    tmp_path: Path, make_hook: HookFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    path = make_hook(tmp_path / "playbook" / "hooks", "guard-x", timeout=45)

    assert _run(tmp_path) == 1

    out = capsys.readouterr().out
    assert _fail_lines(out) == [
        f"FAIL {path}: timeout 45 exceeds 30 s for tool and prompt events ['pre_tool_use']"
    ]
    skipped = [line for line in out.splitlines() if line.startswith("skipped")]
    assert len(skipped) == len(_validate_context.CONSUMER_CONFIG_CHECKS)
    assert any("H16" in line and "H21" in line for line in skipped)


def test_overlong_summary_is_a_fail_line_naming_field_value_and_shape(
    tmp_path: Path, make_hook: HookFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """The H1 shape check of the one-line guardrail (specs/prS-skills-context.md 8.6)."""
    summary = "Never run " + "x" * 140
    bad = make_hook(tmp_path / "playbook" / "hooks", "guard-x", summary=summary)

    assert _run(tmp_path) == 1

    assert _fail_lines(capsys.readouterr().out) == [
        f"FAIL {bad}: summary: expected a single line of 1-120 characters without '{{{{' or "
        f"'{{%', got {summary!r}"
    ]


def test_validate_without_config_tolerates_a_malformed_hook(
    tmp_path: Path, make_hook: HookFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = make_hook(tmp_path / "playbook" / "hooks", "guard-x", events="stop")

    assert _run(tmp_path) == 1

    assert _fail_lines(capsys.readouterr().out) == [
        f"FAIL {bad}: events: expected a list of strings, got 'stop'"
    ]


def test_long_advisory_body_warns_and_passes(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # §C.4.2: every enabled hook's advisory lands in AGENTS.md; keep each one short.
    repo = make_synthetic_repo(tmp_path)
    hooks = repo / "playbook" / "hooks"
    make_hook(hooks, "guard-x", body="x" * 600 + "\n")
    long = make_hook(hooks, "guard-y", body="y" * 601 + "\n")

    assert _run(repo) == 0
    assert capsys.readouterr().err.splitlines() == [
        f"warning: {long}: advisory body is 601 characters; keep it under 600 so the "
        "AGENTS.md Guardrails section stays lean"
    ]


def test_mutates_edited_file_rejected_for_external_handlers(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only an engine builtin may rewrite the edited file (specs/prK-hook-pack.md §E.3).

    A ``HOOK.md`` has no way to claim the capability: the key is unknown (H1).
    """
    repo = make_synthetic_repo(tmp_path)
    handler = {"command": "python", "script": "scripts/fix.py", "mutates_edited_file": True}
    path = make_hook(
        repo / "playbook" / "hooks",
        "fixer",
        scripts=True,
        events=["post_tool_use"],
        decisions=["context", "none"],
        on_error="open",
        handler=handler,
    )

    assert _run(repo) == 1

    assert _fail_lines(capsys.readouterr().out) == [
        f"FAIL {path}: handler.mutates_edited_file: unknown key 'mutates_edited_file'; "
        "allowed: builtin, command, script, args, config"
    ]


@pytest.mark.catalog
def test_overlay_extra_pattern_redos_rejected(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_package: PackageFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An overlay's secret ``extra_patterns`` run on agent text: validate screens each one (§E.4)."""
    repo = make_synthetic_repo(tmp_path)
    name, hooks = _overlay_hooks(make_package)
    shipped = engine_hook_paths()["secret-content-guard"].read_text(encoding="utf-8")
    assert "    extra_patterns: []\n" in shipped
    override = hooks / "safety" / "secret-content-guard" / "HOOK.md"
    override.parent.mkdir(parents=True)
    bad = '    extra_patterns:\n      - {id: acme-token, regex: "(a+)+$"}\n'
    override.write_text(shipped.replace("    extra_patterns: []\n", bad), encoding="utf-8")
    (repo / ".coding-agent-playbook.toml").write_text(_config(overlays=(name,)), encoding="utf-8")

    assert _run(repo) == 1

    assert _fail_lines(capsys.readouterr().out) == [
        f"FAIL {override}: handler.config.extra_patterns: {REDOS}"
    ]
