"""docstring-nonregression: the ``docstrings`` Stop stage and its post-edit bucket (specs/prK-hook-pack.md §F.3.2).

Every case runs the shipped ``HOOK.md`` with the shipped ``python-docstrings``
rule through ``playbook-hook simulate``. The pinned ruff is ``FakeRuff``
behind ``RuntimeDeps.proc``: at Stop it answers the metrics pass's stdin calls
per source text (``by_stdin``), post-edit it answers D1. ``FakeGit`` answers
the ``HEAD`` blobs. No test spawns ruff or git.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.hook_runtime._git_parse import AddedLine
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.registry import load_builtin
from tests.hook_runtime.fakes import FakeRuff, ruff_row
from tests.hook_runtime.handlers.pack_repo import engine_hook, engine_rules
from tests.hook_runtime.handlers.ruff_kit import context, edit, head_git, pin_ruff, value_of
from tests.hook_runtime.handlers.stop_kit import changed_git, reason_lines, stop, stop_payload

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_runtime.fakes import FakeGit
    from tests.hook_runtime.handlers.pack_repo import PackRepo

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "docstring-nonregression"
GATE_ID: Final = "stop-ci-parity-gate"
SRC: Final = "src/x.py"
BASE: Final = 'def load(path):\n    """Load it."""\n    return path\n'
#: A new public def without a docstring on line 6.
NEW_DEF: Final = BASE + "\n\ndef save(path):\n    return path\n"
NEW_PRIVATE: Final = BASE + "\n\ndef _save(path):\n    return path\n"
REMOVED: Final = "def load(path):\n    return path\n"
D103_NEW: Final = ruff_row("D103", 6, "Missing docstring in public function")
D103_LOAD: Final = ruff_row("D103", 1, "Missing docstring in public function")
METRICS_PRECOMMIT: Final = (
    "repos:\n  - repo: local\n    hooks:\n      - id: playbook-metrics\n"
    "        name: metrics\n        entry: playbook metrics --baseline git:HEAD --no-run-tests\n"
)
CODES: Final = "D100,D101,D102,D103,D104,D105,D106,D107"


@pytest.fixture
def repo(pack_repo: PackRepo, ruff_program: Path) -> PackRepo:
    pin_ruff(pack_repo, ruff_program)
    return pack_repo


def _install(
    repo: PackRepo, *, precommit: bool = False, metrics: str = "", hooks: tuple[str, ...] = ()
) -> None:
    if precommit:
        repo.write(".pre-commit-config.yaml", METRICS_PRECOMMIT)
    if metrics:
        repo.write(".coding-agent-playbook.toml", metrics)
    repo.install_pack([GATE_ID, HOOK_ID, *hooks], rules=engine_rules())


def _touched(rel: str = SRC, head: str = BASE) -> FakeGit:
    return changed_git(added=(AddedLine(rel, 1, "x"),), head_blobs={rel: head.encode()})


def _stop(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    ruff: FakeRuff,
    tmp_path: Path,
    git: FakeGit | None = None,
) -> SimulateReport:
    payload = stop_payload(repo, message="Done.")
    return stop(repo, deps, payload, git=git or _touched(), state=tmp_path / "s", proc=ruff)


def _notes(report: SimulateReport) -> list[str]:
    return [n for n in report.trace.combined.user_notes if n.startswith("[docstrings]")]


# --- Stop ------------------------------------------------------------------------------------


def test_new_public_def_without_docstring_context_line(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write(SRC, NEW_DEF)
    _install(repo)
    ruff = FakeRuff(by_stdin={NEW_DEF.encode(): [D103_NEW]})

    report = _stop(repo, deps, ruff, tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    assert _notes(report) == ['[docstrings] "src/x.py" ruff:docstrings 0 -> 1 (D103 save)']
    assert ruff.kinds() == ["metrics", "metrics"]  # one call per side; the details reuse them
    assert {call.input for call in ruff.calls} == {NEW_DEF.encode(), BASE.encode()}


def test_new_private_def_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write(SRC, NEW_PRIVATE)
    _install(repo)

    report = _stop(repo, deps, FakeRuff(), tmp_path)  # ruff reports no D1xx on a _private def

    assert (report.trace.combined.decision, _notes(report)) == (Decision.NONE, [])


def test_removed_docstring_deny_when_metrics_precommit_and_ruff_violations_selected(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write(SRC, REMOVED)
    _install(repo, precommit=True, metrics='[metrics]\nextend_select = ["ruff_violations"]\n')
    ruff = FakeRuff(by_stdin={REMOVED.encode(): [D103_LOAD]})

    report = _stop(repo, deps, ruff, tmp_path)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1:] == [
        '[docstrings] "src/x.py" ruff:docstrings 0 -> 1 (D103 load)'
    ]


def test_removed_docstring_context_without_selection(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write(SRC, REMOVED)
    _install(repo, precommit=True)  # the twin does not run ruff_violations: never a deny
    ruff = FakeRuff(by_stdin={REMOVED.encode(): [D103_LOAD]})

    report = _stop(repo, deps, ruff, tmp_path)

    assert report.trace.combined.decision is Decision.NONE
    assert _notes(report) == ['[docstrings] "src/x.py" ruff:docstrings 0 -> 1 (D103 load)']


def test_body_only_edit_of_legacy_def_silent_stop_and_post_edit(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    edited = REMOVED.replace("return path", "return path.strip()")
    repo.write(SRC, edited)
    _install(repo)
    at_stop = FakeRuff(by_stdin={REMOVED.encode(): [D103_LOAD], edited.encode(): [D103_LOAD]})
    after_edit = FakeRuff(diagnostics=[D103_LOAD])  # the def line (1) did not change

    stop_report = _stop(repo, deps, at_stop, tmp_path, git=_touched(head=REMOVED))
    edit_report = edit(repo, deps(proc=after_edit, git=head_git(REMOVED, SRC)), SRC)

    assert (stop_report.trace.combined.decision, _notes(stop_report)) == (Decision.NONE, [])
    assert (edit_report.trace.combined.decision, context(edit_report)) == (Decision.NONE, [])


def test_strict_mode_summary_only_line(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    summary_only = BASE + '\n\ndef save(path):\n    """Save it."""\n    return path\n'
    repo.write(SRC, summary_only)
    strict = (
        '[metrics]\nextend_select = ["docstring_example"]\n\n'
        "[metrics.thresholds.docstring_example]\nfail = 1.0\n"
    )
    _install(repo, metrics=strict)

    report = _stop(repo, deps, FakeRuff(), tmp_path)

    assert _notes(report) == [
        '[docstrings] "src/x.py"::save needs an intent line + one usage example '
        "(>>>, Example:, or Usage::)"
    ]


def test_tests_dir_edit_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    rel = "tests/test_x.py"
    repo.write(rel, REMOVED)
    _install(repo, precommit=True, metrics='[metrics]\nextend_select = ["ruff_violations"]\n')
    ruff = FakeRuff(by_stdin={REMOVED.encode(): [D103_LOAD]})

    report = _stop(repo, deps, ruff, tmp_path, git=_touched(rel))

    assert (report.trace.combined.decision, _notes(report)) == (Decision.NONE, [])


# --- post-edit -------------------------------------------------------------------------------


def test_post_edit_golden_ruff_json_d103_on_new_def_line_only(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo.write(SRC, NEW_DEF)
    repo.install_pack([HOOK_ID], rules=engine_rules())
    legacy = ruff_row("D100", 1, "Missing docstring in public module")
    ruff = FakeRuff(diagnostics=[legacy, D103_NEW])

    report = edit(repo, deps(proc=ruff, git=head_git(BASE, SRC)), SRC)

    [d1] = ruff.argvs("d1")
    assert value_of(d1, "--extend-select") == CODES
    assert context(report) == [
        'rule python-docstrings (skill python-coding): "src/x.py:6 D103 Missing docstring in public function"'
    ]


def test_lint_feedback_false_drops_codes_from_d1(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo.write(SRC, NEW_DEF)
    per_hook = {HOOK_ID: {"lint_feedback": False}}
    repo.install_pack([HOOK_ID, "post-edit-ruff-format"], rules=engine_rules(), per_hook=per_hook)
    ruff = FakeRuff()  # the project selects no D code, so ruff reports none

    report = edit(repo, deps(proc=ruff, git=head_git(BASE, SRC)), SRC)

    [d1] = ruff.argvs("d1")  # post-edit-ruff-format still asks for the project's own codes
    assert "--extend-select" not in d1
    assert context(report) == []


def test_shipped_hook_matches_its_pack_row() -> None:
    fm = engine_hook(HOOK_ID).frontmatter
    stop_handler, post_edit = fm.handlers["stop"], fm.handlers["post_tool_use"]
    assert stop_handler.builtin is not None and post_edit.builtin is not None

    assert (fm.tier, fm.linked_rule) == ("default", "python-docstrings")
    assert stop_handler.config == {"stage": "docstrings"}
    assert set(post_edit.config) <= set(load_builtin(post_edit.builtin).config_schema)
