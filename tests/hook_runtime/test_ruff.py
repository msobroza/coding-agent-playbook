"""The ruff seam of the §E.3 post-edit pipeline (specs/prK-hook-pack.md §E.3).

``_ruff`` is pure apart from ``RuffRunner``, which reaches ruff only through
the injected ``ProcPort`` (``FakeRuff`` here): argv builders, the D1 memo,
the pin check, the JSON parse, changed lines and ruff's selector semantics.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime._event_memo import EventMemo
from coding_agent_playbook.hook_runtime._ruff import (
    NEVER_FIX,
    RUFF_TIMEOUT_S,
    RuffDiagnostic,
    RuffFailure,
    RuffPin,
    RuffRunner,
    changed_lines,
    d1_args,
    fix_args,
    format_args,
    format_check_args,
    intersect_selectors,
    parse_diagnostics,
    rewritten,
    ruff_diagnostics_for,
    ruff_pin,
    selector_matches,
)
from coding_agent_playbook.hook_runtime.config.pin import MachinePins, ToolPin, tool_signature
from coding_agent_playbook.hook_runtime.proc import ProcResult, SubprocessProc
from tests.hook_runtime.dispatch_kit import POST, dispatch
from tests.hook_runtime.fakes import FakeRuff, ruff_row
from tests.hook_runtime.guard_repo import hook_record

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from tests.hook_runtime.fakes import FakeHandlerResolver
    from tests.hook_runtime.guard_repo import GuardRepo

RUFF = "/venv/bin/ruff"


def _runner(ruff: FakeRuff, drop: frozenset[str] = frozenset()) -> RuffRunner:
    return RuffRunner(ruff, RuffPin((RUFF,), drop), cwd="/repo")


# --- changed lines -------------------------------------------------------------------------


def test_changed_lines_insert_replace_and_missing_head_means_all() -> None:
    head = "import os\n\ndef f():\n    return 1\n"
    new = "import os\nimport sys\n\ndef f():\n    return 2\n"

    assert changed_lines(head, new) == {2, 5}  # one inserted, one replaced
    assert changed_lines(head, "import os\n\ndef f():\n") == set()  # deletions only
    assert changed_lines(None, new) == {1, 2, 3, 4, 5}  # new or untracked: every line


# --- D1 ------------------------------------------------------------------------------------


def test_d1_argv_has_no_fix_exit_zero_force_exclude_json_extend_select() -> None:
    args = d1_args("/repo/src/app.py", ["UP045", "B006", "B006"], drop=["UP045"])

    assert args == [
        "check",
        "--no-fix",
        "--exit-zero",
        "--force-exclude",
        "--output-format",
        "json",
        "--extend-select",
        "B006",
        "--",
        "/repo/src/app.py",
    ]
    assert "--extend-select" not in d1_args("/repo/a.py", [])  # project selection only


def test_d1_memo_runs_once_per_path_and_sha() -> None:
    ruff = FakeRuff(diagnostics=[ruff_row("F821", 3, "Undefined name `x`")])
    runner, memo = _runner(ruff), EventMemo()

    first = ruff_diagnostics_for(runner, memo, "/repo/a.py", b"x\n", ["B006"])
    again = ruff_diagnostics_for(runner, memo, "/repo/a.py", b"x\n", ["B006"])
    changed = ruff_diagnostics_for(runner, memo, "/repo/a.py", b"y\n", ["B006"])
    other = ruff_diagnostics_for(runner, memo, "/repo/b.py", b"x\n", ["B006"])

    assert first == again == changed == other == [RuffDiagnostic("F821", 3, "Undefined name `x`")]
    assert len(ruff.argvs("d1")) == 3  # (a.py, x), (a.py, y), (b.py, x)
    assert ruff_diagnostics_for(runner, EventMemo(), "/repo/a.py", b"x\n", []) == first
    assert len(ruff.argvs("d1")) == 4  # a new event, a new memo


def test_event_memo_is_shared_by_every_hook_of_one_event(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> None:
    """The D1 memo's home: one per dispatch, handed to each hook's context."""
    repo.install(
        hook_record("lint-a", events=["post_tool_use"], on_error="open"),
        hook_record("lint-b", events=["post_tool_use"], on_error="open"),
    )
    seen: list[EventMemo] = []
    computed: list[str] = []

    def handler(ev: CanonicalEvent, ctx: HandlerContext) -> None:
        seen.append(ctx.memo)
        ctx.memo.get_or_compute("d1", lambda: computed.append(ctx.hook.id))

    resolver.handlers.update({"lint-a": handler, "lint-b": handler})
    dispatch(make_deps(), repo, POST, tool="Edit", tool_response={"success": True})
    dispatch(make_deps(), repo, POST, tool="Edit", tool_response={"success": True})

    assert seen[0] is seen[1] and seen[2] is seen[3] and seen[0] is not seen[2]
    assert computed == ["lint-a", "lint-a"]  # once per event, by whichever hook asked first


def test_d1_leaves_dropped_codes_out_of_the_argv() -> None:
    ruff = FakeRuff()

    ruff_diagnostics_for(
        _runner(ruff, frozenset({"DOC201"})), EventMemo(), "/r/a.py", b"", ["DOC201", "B006"]
    )

    [args] = ruff.argvs("d1")
    assert args[args.index("--extend-select") + 1] == "B006"


def test_d1_error_exit_or_bad_json_is_a_failure() -> None:
    with pytest.raises(RuffFailure) as failed:
        ruff_diagnostics_for(_runner(FakeRuff(d1_exit=2)), EventMemo(), "/r/a.py", b"", [])
    assert failed.value.kind == "error"
    with pytest.raises(RuffFailure):
        parse_diagnostics(b"not json")
    with pytest.raises(RuffFailure):
        parse_diagnostics(b'[{"code": "F401"}]')  # no location


def test_parse_reads_codes_rows_and_both_syntax_error_shapes() -> None:
    rows = [ruff_row("F401", 1, "unused"), ruff_row(None, 3, "x"), ruff_row("invalid-syntax", 4)]

    parsed = parse_diagnostics(json.dumps(rows).encode())

    assert [(d.label, d.row, d.is_syntax_error) for d in parsed] == [
        ("F401", 1, False),
        ("syntax-error", 3, True),
        ("invalid-syntax", 4, True),
    ]


# --- the runner and the pin ------------------------------------------------------------------


def test_run_ruff_timeout_is_2s_and_failure_is_open() -> None:
    ruff = FakeRuff(timeouts={"d1"})

    with pytest.raises(RuffFailure) as failed:
        _runner(ruff).run(d1_args("/repo/a.py", []))

    assert failed.value.kind == "timeout"
    assert RUFF_TIMEOUT_S == 2.0
    [call] = ruff.calls
    assert call.timeout == 2.0 and call.cwd == "/repo" and call.argv[0] == RUFF


def test_missing_program_is_a_failure_not_a_crash(tmp_path: Path) -> None:
    gone = RuffRunner(SubprocessProc(), RuffPin((str(tmp_path / "no-ruff"),)), cwd=str(tmp_path))

    with pytest.raises(RuffFailure) as failed:
        gone.run(["format", "--", "a.py"])

    assert failed.value.kind == "missing"


def test_pin_sig_mismatch_skips(tmp_path: Path) -> None:
    program = tmp_path / "ruff"
    program.write_bytes(b"#!/bin/sh\n")
    sig = tool_signature(str(program))
    pins = MachinePins("0.1", {"ruff": ToolPin((str(program),), sig, frozenset({"X1"}))}, {})

    assert ruff_pin(pins) == RuffPin((str(program),), frozenset({"X1"}))
    program.write_bytes(b"#!/bin/sh\necho overwritten\n")  # the agent replaced the binary
    assert ruff_pin(pins) == "changed"
    assert ruff_pin(MachinePins("0.1", {}, {})) == "missing"
    assert ruff_pin(None) == "missing"


# --- M1 and the HEAD check -------------------------------------------------------------------


def test_fix_args_select_only_safe_rules_and_never_fix_unused_names() -> None:
    args = fix_args("src/a.py", ["I", "UP"], ["UP007"])

    assert args[: args.index("--select")] == [
        "check",
        "--fix-only",
        "--force-exclude",
        "--no-unsafe-fixes",
    ]
    assert args[args.index("--select") + 1] == "I,UP"
    assert args[args.index("--ignore") + 1] == "UP007"
    assert args[args.index("--unfixable") + 1] == ",".join(NEVER_FIX) == "F401,F841,F811"
    assert args[-3:] == ["--stdin-filename", "src/a.py", "-"]  # the file's bytes on stdin


def test_format_reads_the_edited_text_from_stdin_as_its_repo_path() -> None:
    assert format_args("src/a.py") == [
        "format",
        "--force-exclude",
        "--stdin-filename",
        "src/a.py",
        "-",
    ]


@pytest.mark.parametrize(
    ("returncode", "stdout", "expected"),
    [
        (0, b"x = 1\n", b"x = 1\n"),
        (2, b"", b"x=1\n"),  # a parse error: the text stays as it was
        (0, b"", b"x=1\n"),  # never an empty file over content
    ],
)
def test_rewritten_takes_stdout_only_from_a_clean_run(
    returncode: int, stdout: bytes, expected: bytes
) -> None:
    done = ProcResult(("ruff", "format"), returncode, stdout)

    assert rewritten(done, b"x=1\n") == expected


def test_format_check_reads_head_text_from_stdin_as_its_repo_path() -> None:
    assert format_check_args("src/a.py") == [
        "format",
        "--check",
        "--force-exclude",
        "--stdin-filename",
        "src/a.py",
        "-",
    ]


# --- selectors -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("selector", "code", "selected"),
    [
        ("ALL", "F401", True),
        ("I", "I001", True),
        ("I", "INP001", False),
        ("UP", "UP006", True),
        ("UP0", "UP006", True),
        ("UP04", "UP006", False),
        ("E", "EM101", False),
        ("E", "E501", True),
        ("PL", "PLR0911", True),
        ("PLR09", "PLR0911", True),
        ("PLR", "PLW0120", False),
        ("C", "C901", True),
        ("C", "C401", True),
        ("TCH", "TC001", False),
    ],
)
def test_selector_matches_is_prefix_aware(selector: str, code: str, selected: bool) -> None:
    assert selector_matches(selector, code) is selected


def test_intersect_keeps_covered_prefixes_and_narrower_selectors() -> None:
    assert intersect_selectors(["I", "UP"], ["ALL"]) == ["I", "UP"]
    assert intersect_selectors(["I", "UP"], ["E", "F", "I", "UP006"]) == ["I", "UP006"]
    assert intersect_selectors(["I", "UP"], ["E4", "E7", "E9", "F", "INP"]) == []
