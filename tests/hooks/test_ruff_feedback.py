"""post-edit-ruff-format on the shared post-edit pipeline (specs/prK-hook-pack.md §E.3).

Every case runs the shipped ``HOOK.md`` through ``playbook-hook simulate
post_tool_use`` against a repository synced with it. The pinned ruff is
``FakeRuff`` behind ``RuntimeDeps.proc`` (``machine.json`` names a stub file,
so the pin's stat signature is real); ``FakeGit`` answers the HEAD blob. No
test spawns ruff or git. The ``perf_*`` goldens pin the parse and the wire.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.guard_config import DetectInputs
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.registry import load_builtin
from tests.hook_runtime.fakes import FakeRuff, ruff_row
from tests.hooks.pack_repo import PackRepo, engine_hook, engine_hook_paths, engine_rules
from tests.hooks.ruff_kit import context, edit, head_git, pin_ruff, value_of

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase
    from tests.hook_runtime.fakes import FakeGit

    type Payload = Callable[[str, str, str], HookPayloadCase]

HOOK_ID: Final = "post-edit-ruff-format"
APP: Final = "src/app.py"
PYPROJECT: Final = '[tool.ruff.lint]\nselect = ["E", "F", "I", "UP"]\nignore = ["UP007"]\n'
HEAD: Final = "import os\n\n\ndef f():\n    return os.sep\n"
#: The agent's edit: line 6 is new.
EDITED: Final = HEAD + "x = undefined_name\n"
PREFIX: Final = "ruff (CI fails on this): "


def fix_text(text: str) -> str:
    """The scripted M1 of the M1-then-M2 case: one sorted-import change."""
    return text.replace("import os\n", "import os\n\nimport sys\n", 1)


@pytest.fixture
def repo(pack_repo: PackRepo, ruff_program: Path) -> PackRepo:
    """post-edit-ruff-format on, the project selecting E/F/I/UP, ruff pinned."""
    pack_repo.write("pyproject.toml", PYPROJECT)
    pack_repo.write(APP, EDITED)
    pack_repo.install_pack([HOOK_ID])
    _pin(pack_repo, ruff_program)
    return pack_repo


def _pin(repo: PackRepo, program: Path) -> None:
    pin_ruff(repo, program)


def _git(head: str | None = HEAD, rel: str = APP) -> FakeGit:
    return head_git(head, rel)


def _edit(
    repo: PackRepo, deps: RuntimeDeps, rel: str = APP, *, state: Path | None = None
) -> SimulateReport:
    return edit(repo, deps, rel, state=state)


_context = context
_value = value_of


# --- M1 / M2: anti-churn ---------------------------------------------------------------------


def test_clean_at_head_file_gets_m1_then_m2(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    ruff = FakeRuff(fix=fix_text, reformat=lambda text: text + "# formatted\n")

    report = _edit(repo, deps(proc=ruff, git=_git()))

    # M1 and M2 rewrite the file's bytes through stdin; HEAD is judged only once they changed it
    assert ruff.kinds() == ["fix", "format", "format-check", "d1"]
    fix, fmt, check = (c for c in ruff.calls if ruff.kind(c.argv[1:]) != "d1")
    assert fix.input == EDITED.encode() and fmt.input == fix_text(EDITED).encode()
    assert check.input == HEAD.encode() and check.cwd == str(repo.root)
    assert _value(fix.argv, "--select") == "I,UP"
    assert _value(fix.argv, "--ignore") == "UP007"  # the project's ignore survives the CLI --select
    assert _value(fmt.argv, "--stdin-filename") == APP
    text = (repo.root / APP).read_text(encoding="utf-8")
    assert "import sys" in text and text.endswith("# formatted\n")  # lint fixes, then format
    assert report.trace.combined.decision is Decision.NONE  # silent on success


def test_edit_m1_m2_leave_unchanged_needs_no_head_check(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    """Finding #5: the one format call decides; HEAD's verdict cannot matter when nothing changes."""
    ruff = FakeRuff(format_clean=False)
    before = (repo.root / APP).stat().st_mtime_ns

    _edit(repo, deps(proc=ruff, git=_git()))

    assert ruff.kinds() == ["fix", "format", "d1"]
    assert (repo.root / APP).read_text(encoding="utf-8") == EDITED
    assert (repo.root / APP).stat().st_mtime_ns == before  # no write at all


def test_unformatted_at_head_file_untouched_and_reported(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    ruff = FakeRuff(
        format_clean=False,
        reformat=lambda text: text + "# formatted\n",
        diagnostics=[ruff_row("F821", 6, "Undefined name `undefined_name`")],
    )

    report = _edit(repo, deps(proc=ruff, git=_git()))

    assert ruff.kinds() == ["fix", "format", "format-check", "d1"]
    assert (repo.root / APP).read_text(encoding="utf-8") == EDITED  # never reformatted
    assert _context(report) == [f'{PREFIX}"src/app.py:6 F821 Undefined name `undefined_name`"']


def test_import_only_edit_keeps_import_no_F_in_m1_argv(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo.write(APP, "import json\n" + HEAD)  # the import first, its use in the next Edit
    ruff = FakeRuff(diagnostics=[ruff_row("F401", 1, "`json` imported but unused")])

    report = _edit(repo, deps(proc=ruff, git=_git()))

    [fix] = ruff.argvs("fix")
    selected = _value(fix, "--select").split(",")
    assert not any(code.startswith("F") for code in selected)
    assert _value(fix, "--unfixable") == "F401,F841,F811"
    assert (repo.root / APP).read_text(encoding="utf-8").startswith("import json\n")
    assert _context(report) == [f'{PREFIX}"src/app.py:1 F401 `json` imported but unused"']


def test_format_verdict_cached_per_head_blob(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    ruff = FakeRuff(reformat=lambda text: text + "# formatted\n")

    _edit(repo, deps(proc=ruff, git=_git()), state=tmp_path / "state")
    _edit(repo, deps(proc=ruff, git=_git()), state=tmp_path / "state")

    assert ruff.kinds().count("format-check") == 1
    assert ruff.kinds().count("format") == 2
    assert (repo.root / APP).read_text(encoding="utf-8").endswith("# formatted\n# formatted\n")


def test_legacy_verdict_cached_skips_m1_m2_on_the_next_edit(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    ruff = FakeRuff(format_clean=False, reformat=lambda text: text + "# formatted\n")

    _edit(repo, deps(proc=ruff, git=_git()), state=tmp_path / "state")
    _edit(repo, deps(proc=ruff, git=_git()), state=tmp_path / "state")

    assert ruff.kinds() == ["fix", "format", "format-check", "d1", "d1"]
    assert (repo.root / APP).read_text(encoding="utf-8") == EDITED


def test_safe_fix_allowlist_narrows_and_never_widens(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    pack_repo.write("pyproject.toml", PYPROJECT)
    pack_repo.write(APP, EDITED)
    pack_repo.install_pack([HOOK_ID], per_hook={HOOK_ID: {"safe_fix_allowlist": ["I", "F"]}})
    _pin(pack_repo, ruff_program)
    ruff = FakeRuff()

    _edit(pack_repo, deps(proc=ruff, git=_git()))

    assert _value(ruff.argvs("fix")[0], "--select") == "I"


def test_project_on_ruff_defaults_gets_format_but_no_fixes(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    pack_repo.write(APP, EDITED)  # no ruff config: the version-dependent default selection
    pack_repo.install_pack([HOOK_ID])
    _pin(pack_repo, ruff_program)
    ruff = FakeRuff()

    _edit(pack_repo, deps(proc=ruff, git=_git()))

    assert ruff.kinds() == ["format", "d1"]


# --- D1 on the changed lines: partition, dedupe, cap -----------------------------------------


def test_new_untracked_file_all_lines_changed(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    ruff = FakeRuff(diagnostics=[ruff_row("E711", 2, "Comparison to `None`")])

    report = _edit(repo, deps(proc=ruff, git=_git(None)))

    assert ruff.kinds() == ["fix", "format", "d1"]  # nothing at HEAD to judge: always clean
    assert _context(report) == [f'{PREFIX}"src/app.py:2 E711 Comparison to `None`"']


def test_diagnostics_on_unchanged_lines_are_dropped(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    rows = [ruff_row("E711", 4, "legacy"), ruff_row("F821", 6, "Undefined name")]

    report = _edit(repo, deps(proc=FakeRuff(diagnostics=rows), git=_git()))

    assert _context(report) == [f'{PREFIX}"src/app.py:6 F821 Undefined name"']


def test_seven_project_diagnostics_report_five(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo.write(APP, "".join(f"v{i} = undefined_{i}\n" for i in range(7)))
    rows = [
        ruff_row("F821", row, f"Undefined name `undefined_{row - 1}`") for row in range(7, 0, -1)
    ]

    report = _edit(repo, deps(proc=FakeRuff(diagnostics=rows), git=_git(None)))

    context = _context(report)
    assert len(context) == 5
    assert [line.split(":")[2].split()[0] for line in context] == ["1", "2", "3", "4", "5"]


def test_same_diagnostic_twice_reported_once(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    rows = [ruff_row("F821", 6, "Undefined name `undefined_name`")]
    state = tmp_path / "state"

    first = _edit(repo, deps(proc=FakeRuff(diagnostics=rows), git=_git()), state=state)
    repo.write(APP, "# a line above shifts the finding\n" + EDITED)
    shifted = [ruff_row("F821", 7, "Undefined name `undefined_name`")]
    second = _edit(repo, deps(proc=FakeRuff(diagnostics=shifted), git=_git()), state=state)

    assert len(_context(first)) == 1
    assert second.trace.combined.decision is Decision.NONE  # same file, code and line text


def test_syntax_error_code_null_lands_in_bucket_1(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo.write(APP, HEAD.replace("def f():", "def f(:"))
    rows = [ruff_row(None, 5, "Expected ')', found newline")]  # ruff points past the edit

    report = _edit(repo, deps(proc=FakeRuff(diagnostics=rows), git=_git()))

    assert _context(report) == [
        f"{PREFIX}\"src/app.py:5 syntax-error Expected ')', found newline\""
    ]


# --- the shared-call invariant: every consumer on, one D1 ------------------------------------

#: Every §E.3 ruff consumer shipped so far.
ALL_CONSUMERS: Final = (
    HOOK_ID,
    "error-handling-lint-feedback",
    "typing-lint-feedback",
    "pytest-conventions-feedback",
)


def _install_all(repo: PackRepo, program: Path, select: str = '["E", "F", "I", "UP"]') -> None:
    repo.write("pyproject.toml", f"[tool.ruff.lint]\nselect = {select}\n")
    facts = {"python_version": "3.12", "frameworks": {"pytest": ">=8"}}
    repo.install_pack(list(ALL_CONSUMERS), rules=engine_rules(), detect=DetectInputs(facts=facts))
    _pin(repo, program)


@pytest.mark.parametrize(("rel", "consumers"), [("tests/test_app.py", 4), ("src/app.py", 3)])
def test_one_d1_argv_per_event_with_all_consumers_enabled(
    pack_repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    ruff_program: Path,
    rel: str,
    consumers: int,
) -> None:
    """§E.3 Done-when: exactly one D1 per edited file, whatever the number of consumers."""
    _install_all(pack_repo, ruff_program)
    pack_repo.write(rel, "x = 1\n")
    ruff = FakeRuff()

    report = _edit(pack_repo, deps(proc=ruff, git=_git(None, rel)), rel)

    [d1] = ruff.argvs("d1")
    extended = _value(d1, "--extend-select").split(",")
    ran = [o.hook_id for o in report.trace.combined.outcomes]
    assert len(ran) == consumers and ran[0] == HOOK_ID  # M1/M2 first, then the lint hooks
    assert ruff.kinds() == ["fix", "format", "d1"]
    assert ("PT009" in extended) is rel.startswith("tests/")  # U is per file
    assert {"E722", "ANN001", "UP046"} <= set(extended)


# --- §F's companions: the quality and docstrings buckets (§F.2.2, §F.3.2) ----------------------

QUALITY_ID: Final = "clean-code-metrics-nonregression"
DOCSTRINGS_ID: Final = "docstring-nonregression"
QUALITY_CODES: Final = {"C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915"}


def _install_companions(
    repo: PackRepo, program: Path, *, select: str, metrics: str, drops: list[str] | None = None
) -> None:
    repo.write("pyproject.toml", f"[tool.ruff.lint]\nselect = {select}\n")
    repo.write(".coding-agent-playbook.toml", metrics)
    repo.write(APP, EDITED)
    hooks = [HOOK_ID, QUALITY_ID, DOCSTRINGS_ID]
    repo.install_pack(hooks, rules=engine_rules())  # both companions as shipped: on
    pin_ruff(repo, program, drops={"ruff": drops} if drops else None)


def _config_flags(args: tuple[str, ...]) -> list[str]:
    return [args[i + 1] for i, arg in enumerate(args) if arg == "--config"]


def test_one_d1_argv_carries_quality_and_docstring_codes_and_config_override(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    metrics = '[metrics.ruff_violations]\nconfig = { "lint.mccabe.max-complexity" = 10 }\n'
    _install_companions(pack_repo, ruff_program, select='["E", "F"]', metrics=metrics)
    ruff = FakeRuff(diagnostics=[ruff_row("C901", 6, "`f` is too complex (12 > 10)")])

    report = _edit(pack_repo, deps(proc=ruff, git=_git()))

    [d1] = ruff.argvs("d1")
    extended = set(_value(d1, "--extend-select").split(","))
    assert {*QUALITY_CODES, "D100", "D107"} <= extended
    assert _config_flags(d1) == ["lint.mccabe.max-complexity=10"]
    assert ruff.kinds().count("preview") == 0
    assert _context(report) == ['quality: "src/app.py:6 C901 `f` is too complex (12 > 10)"']


def test_no_override_when_project_selects_c901(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    metrics = (
        "[metrics.ruff_violations]\n"
        'config = { "lint.mccabe.max-complexity" = 10, "lint.pylint.max-args" = 5 }\n'
    )
    _install_companions(pack_repo, ruff_program, select='["E", "F", "C901"]', metrics=metrics)
    ruff = FakeRuff()

    _edit(pack_repo, deps(proc=ruff, git=_git()))

    [d1] = ruff.argvs("d1")
    assert _config_flags(d1) == ["lint.pylint.max-args=5"]  # C901's threshold is the project's


def test_plr1702_only_via_separate_preview_call(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    metrics = (
        '[metrics.ruff_violations]\nfamilies = { quality = ["C901", "PLR1702"] }\npreview = true\n'
    )
    _install_companions(
        pack_repo, ruff_program, select='["E", "F"]', metrics=metrics, drops=["PLR1702"]
    )
    nested = ruff_row("PLR1702", 6, "Too many nested blocks (6 > 5)")
    ruff = FakeRuff(preview_diagnostics=[nested])

    report = _edit(pack_repo, deps(proc=ruff, git=_git()))

    [d1], [preview] = ruff.argvs("d1"), ruff.argvs("preview")
    assert "PLR1702" not in _value(d1, "--extend-select").split(",")
    assert "--preview" not in d1
    assert (_value(preview, "--select"), preview[-2:]) == (
        "PLR1702",
        ("--", str(pack_repo.root / APP)),
    )
    assert _context(report) == ['quality: "src/app.py:6 PLR1702 Too many nested blocks (6 > 5)"']


def test_quality_companion_on_by_default_without_preview(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    """The shipped companion rides D1 with the quality codes; PLR1702 stays opt-in (preview)."""
    pack_repo.write("pyproject.toml", '[tool.ruff.lint]\nselect = ["E", "F"]\n')
    pack_repo.write(APP, EDITED)
    pack_repo.install_pack([HOOK_ID, QUALITY_ID])
    _pin(pack_repo, ruff_program)
    ruff = FakeRuff(diagnostics=[ruff_row("PLR0913", 6, "Too many arguments (6 > 5)")])

    report = _edit(pack_repo, deps(proc=ruff, git=_git()))

    [d1] = ruff.argvs("d1")
    assert set(_value(d1, "--extend-select").split(",")) == QUALITY_CODES
    assert "--preview" not in d1 and ruff.kinds().count("preview") == 0
    assert _context(report) == ['quality: "src/app.py:6 PLR0913 Too many arguments (6 > 5)"']


def test_quality_companion_lint_feedback_false_adds_nothing(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    pack_repo.write("pyproject.toml", '[tool.ruff.lint]\nselect = ["E", "F"]\n')
    pack_repo.write(APP, EDITED)
    pack_repo.install_pack([HOOK_ID, QUALITY_ID], per_hook={QUALITY_ID: {"lint_feedback": False}})
    _pin(pack_repo, ruff_program)
    ruff = FakeRuff()

    _edit(pack_repo, deps(proc=ruff, git=_git()))

    [d1] = ruff.argvs("d1")
    assert "--extend-select" not in d1 and "--config" not in d1


def test_eight_line_total_cap_bucket_1_first(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path
) -> None:
    """At most 5 lines from bucket 1 and 8 per event: bucket 1 first, then by line.

    The cap keeps lines 8-10 and drops line 11; each hook then shows its own
    lines, in handler order (post-edit first).
    """
    _install_all(pack_repo, ruff_program, select='["F"]')
    pack_repo.write(APP, "".join(f"v{i} = {i}\n" for i in range(12)))
    rows = [ruff_row("F821", row, f"Undefined name `u{row}`") for row in range(7, 0, -1)]
    rows += [
        ruff_row("TRY401", 11, "Redundant exception object"),
        ruff_row("S110", 10, "`try`-`except`-`pass` detected"),
        ruff_row("B006", 9, "Do not use mutable data structures for argument defaults"),
        ruff_row("BLE001", 8, "Do not catch blind exception"),
    ]

    report = _edit(pack_repo, deps(proc=FakeRuff(diagnostics=rows), git=_git(None)))

    shown = [(line.split(":")[0], line.split(":")[2].split()[0]) for line in _context(report)]
    assert shown == [
        *[("ruff (CI fails on this)", str(row)) for row in range(1, 6)],
        ("rule python-error-handling", "8"),
        ("rule python-error-handling", "10"),
        ("rule python-typing", "9"),
    ]


# --- eligibility: no work off Python files in the repo ---------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "README.md",
        ".env.settings.py",
        "src/coding_agent_playbook/resources/eval_tasks/t1/setup/app.py",
    ],
    ids=["markdown", "secret-path", "eval-fixture"],
)
def test_ineligible_edit_spawns_no_subprocess(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], rel: str
) -> None:
    repo.write(rel, "x = 1\n")
    git = _git()

    report = _edit(repo, deps(git=git), rel)  # FakeProc: any spawn fails the test

    assert report.trace.combined.decision is Decision.NONE
    assert git.calls == []


def test_out_of_repo_path_is_skipped(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere" / "x.py"
    outside.parent.mkdir()
    outside.write_text("x = 1\n", encoding="utf-8")
    git = _git()

    report = _edit(repo, deps(git=git), str(outside))

    assert report.trace.combined.decision is Decision.NONE
    assert git.calls == []


# --- fail open -------------------------------------------------------------------------------


def test_pin_mismatch_skips_with_one_note_per_session(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], ruff_program: Path, tmp_path: Path
) -> None:
    ruff_program.write_bytes(b"#!/bin/sh\necho replaced by the agent\n")
    ruff, state = FakeRuff(), tmp_path / "state"

    first = _edit(repo, deps(proc=ruff, git=_git()), state=state)
    second = _edit(repo, deps(proc=ruff, git=_git()), state=state)

    assert first.trace.combined.user_notes == (
        "ruff changed since the last `playbook sync`; post-edit checks skipped until it is "
        "re-pinned.",
    )
    assert second.trace.combined.user_notes == ()
    assert ruff.calls == []


def test_no_pin_skips_with_a_note(pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    pack_repo.write(APP, EDITED)
    pack_repo.install_pack([HOOK_ID])
    ruff = FakeRuff()

    report = _edit(pack_repo, deps(proc=ruff, git=_git()))

    assert report.trace.combined.user_notes == (
        "ruff is not pinned in this worktree; post-edit checks skipped (run playbook sync).",
    )
    assert ruff.calls == []


def test_ruff_timeout_skips_with_one_note_and_never_blocks(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    ruff, state = FakeRuff(timeouts={"d1"}), tmp_path / "state"

    first = _edit(repo, deps(proc=ruff, git=_git()), state=state)
    second = _edit(repo, deps(proc=ruff, git=_git()), state=state)

    assert first.trace.combined.decision is Decision.NONE
    assert first.trace.combined.user_notes == (
        "ruff timed out; post-edit checks skipped this time.",
    )
    assert second.trace.combined.user_notes == ()
    assert ruff.calls[-1].timeout == 2.0


# --- goldens and the shipped HOOK.md ---------------------------------------------------------


@pytest.mark.parametrize("harness", ["claude_code", "opencode"])
def test_golden_edit_reports_the_new_finding(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload, harness: str
) -> None:
    case = hook_payload(harness, "post_tool_use", "perf_edit_app")
    rows = [ruff_row("E711", 4, "legacy"), ruff_row("F821", 6, "Undefined name `undefined_name`")]

    report = repo.simulate(
        repo.relocate(case),
        deps(proc=FakeRuff(format_clean=False, diagnostics=rows), git=_git()),
        harness=Harness(case.harness),
        event=EventName.POST_TOOL_USE,
    )

    combined, expected = report.trace.combined, case.expected["result"]
    assert (combined.decision.value, list(combined.context)) == (
        expected["decision"],
        expected["context"],
    )
    assert report.trace.wire == case.wire()


def test_hook_md_matches_its_pack_row_and_handler(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§E.0.6 row: default, post_tool_use, auto_fix -> none (context on findings), open."""
    fm = engine_hook(HOOK_ID).frontmatter
    declaration = load_builtin("ruff_post_edit")

    rc = _validate.run(argparse.Namespace(repo_root=str(tmp_path)))

    assert (fm.tier, fm.events, fm.decisions, fm.on_error) == (
        "default",
        ["post_tool_use"],
        ["context", "none"],
        "open",
    )
    assert fm.supports == ["claude_code", "opencode"]
    assert fm.matcher["post_tool_use"].paths == ["*.py", "*.pyi"]
    assert fm.handler is not None and fm.handler.config == {
        "safe_fix_allowlist": ["I", "UP"],
        "max_project_lines": 5,
    }
    assert declaration.mutates_edited_file is True and declaration.mutates_input is False
    assert set(declaration.config_schema) == {"safe_fix_allowlist", "max_project_lines"}
    assert rc == 0
    assert str(engine_hook_paths()[HOOK_ID]) not in capsys.readouterr().err
