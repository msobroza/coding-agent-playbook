"""skill-nudge: name the skill that covers a file the first time a session edits it (specs/prS-skills-context.md 8.5).

Sync derives the per-skill glob table from the rendered member rules
(``hooks.guard_config._tables_skills``); the builtin matches each written path's key against
it, and combine's per-session dedupe shows each skill's line once. Every case
runs the shipped ``HOOK.md`` through ``playbook-hook simulate post_tool_use``;
nothing spawns.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness
from coding_agent_playbook.hook_runtime.state.store import STATE_DIR_NAME
from coding_agent_playbook.sync import pipeline as _sync
from tests._catalog import TEST_FILE_GLOBS
from tests.cli.hook_repo import CONFIG, GUARD_CONFIG, hook_deps
from tests.core_skill_pins.python_tooling import UNGATED_GLOBS
from tests.fakes import FakeGitClient
from tests.hook_runtime.fakes import FakeRuff, ruff_row
from tests.hook_runtime.handlers.pack_repo import engine_hook, engine_rules
from tests.hook_runtime.handlers.ruff_kit import context, edit, head_git, pin_ruff

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_payloads import HookPayloadCase
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "skill-nudge"
LINT_HOOK_ID: Final = "error-handling-lint-feedback"
APP: Final = "src/app.py"
TEST_APP: Final = "tests/test_app.py"
#: Principle skills that match every Python file, as eight core skills would (D41).
PRINCIPLE_SKILLS: Final = (
    "python-coding",
    "design-patterns",
    "python-architecture",
    "python-documentation",
    "ml-data",
)
NOTEBOOK: Final = "notebooks/explore.ipynb"


def _install_six_skill_pack(pack_repo: PackRepo) -> None:
    """Five ``**/*.py`` principle skills, then python-testing on the shared test-file set."""
    principle = [{"id": skill_id, "globs": ["**/*.py"]} for skill_id in PRINCIPLE_SKILLS]
    testing = {"id": "python-testing", "globs": list(TEST_FILE_GLOBS)}
    pack_repo.install_pack([HOOK_ID], handler_config={HOOK_ID: {"skills": [*principle, testing]}})


def _reference_probe_rules() -> list[Rule]:
    """Every core rule but the Domino-gated ones: the reference probe has no Domino marker.

    The Domino skills' members all gate on ``domino_project`` (prU D63), so sync never
    puts them in this repo's table; keeping them would change every line below.
    """
    return [rule for rule in engine_rules() if "domino_project" not in rule.frontmatter.applies_if]


def _line(skill_id: str) -> str:
    return f"Conventions for this file: skill {skill_id}."


#: Every core skill with members, as in the reference probe (FastAPI + pytest + ML):
#: ``**/*.py`` reaches design-patterns, ml-data, python-architecture, python-coding and
#: python-tooling; tests reach python-testing. On ``src/app.py`` python-architecture
#: (arch-composition-root) and web-application (fastapi-app-wiring) rank first: ``**/app.py``
#: is the most specific glob that matched (D41), and the ties keep config order. Five lines
#: fill the per-hook cap, so python-tooling waits for the next matching edit.
SOURCE_LINES: Final = [
    _line("python-architecture"),
    _line("web-application"),
    _line("design-patterns"),
    _line("ml-data"),
    _line("python-coding"),
]
#: The source skill the five-line cap cuts from the first edit of ``src/app.py``.
CUT_SOURCE_LINE: Final = _line("python-tooling")
#: python-architecture's member globs in member order: Python files, the composition-root
#: file names (arch-composition-root), then the domain and application packages.
ARCHITECTURE_GLOBS: Final = [
    "**/*.py",
    "**/main.py",
    "**/app.py",
    "**/__main__.py",
    "**/deps.py",
    "**/dependencies.py",
    "**/container.py",
    "**/bootstrap.py",
    "**/wiring.py",
    "**/cli.py",
    "**/domain/**/*.py",
    "**/models/**/*.py",
    "**/entities/**/*.py",
    "**/domain.py",
    "**/models.py",
    "**/services/**/*.py",
    "**/application/**/*.py",
]


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    """skill-nudge on, its table derived from every core rule outside the Domino skills."""
    pack_repo.install_pack([HOOK_ID], rules=_reference_probe_rules())
    return pack_repo


@pytest.fixture
def state(tmp_path: Path) -> Path:
    """One session's state dir, kept across simulations."""
    return tmp_path / "state"


def test_first_edit_of_a_python_file_names_python_coding(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    report = edit(repo, deps(), APP, state=state)

    assert report.trace.combined.decision is Decision.CONTEXT
    assert context(report) == SOURCE_LINES


def test_second_edit_in_the_same_session_is_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    edit(repo, deps(), APP, state=state)

    second = edit(repo, deps(), APP, state=state)
    third = edit(repo, deps(), APP, state=state)
    test_file = edit(repo, deps(), TEST_APP, state=state)

    assert context(second) == [CUT_SOURCE_LINE]  # the line the cap cut, never lost
    assert third.trace.combined.decision is Decision.NONE
    assert context(test_file) == [_line("python-testing")]  # spec 8.10 item 6


def test_test_file_names_testing_and_coding_once_each(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    first = edit(repo, deps(), TEST_APP, state=state)
    source = edit(repo, deps(), APP, state=state)
    again = edit(repo, deps(), TEST_APP, state=state)

    # D41: tests/**/*.py ranks python-testing and web-application first, then the
    # ``**/*.py`` ties in config order; the five-line cap cuts python-coding and
    # python-tooling, which the next source edit then names.
    assert context(first) == [
        _line("python-testing"),
        _line("web-application"),
        _line("design-patterns"),
        _line("ml-data"),
        _line("python-architecture"),
    ]
    assert context(source) == [_line("python-coding"), CUT_SOURCE_LINE]
    assert again.trace.combined.decision is Decision.NONE


@pytest.mark.parametrize(
    "test_file",
    ["tests/test_x.py", "tests/helpers.py", "tests/unit/factories.py"],
    ids=["name-glob", "tests-dir-glob", "nested-tests-dir-glob"],
)
def test_test_file_edit_ranks_testing_first_and_keeps_the_five_line_cap(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, test_file: str
) -> None:
    """D41: six skills match, the most specific glob ranks first, ties keep config order."""
    _install_six_skill_pack(pack_repo)

    report = edit(pack_repo, deps(), test_file, state=state)

    assert context(report) == [
        _line("python-testing"),
        _line("python-coding"),
        _line("design-patterns"),
        _line("python-architecture"),
        _line("python-documentation"),
    ]


def test_cut_skill_shows_on_the_next_matching_edit(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    """D41 keeps the cap and the rank picks the line it cuts; the cut skill is not lost.

    The cap burns no dedupe key, so the sixth skill reaches the next edit.
    """
    _install_six_skill_pack(pack_repo)
    edit(pack_repo, deps(), "tests/test_x.py", state=state)

    report = edit(pack_repo, deps(), APP, state=state)

    assert context(report) == [_line("ml-data")]


def test_new_session_nudges_again(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    edit(repo, deps(), APP, state=state)

    other = edit(repo, deps(), APP, state=state, session_id="a-later-session")

    assert context(other) == SOURCE_LINES


def test_notebook_edit_names_ml_data(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    """Spec 12.2: the ml-data members glob ``**/*.ipynb``, and NotebookEdit reaches the hook."""
    tool_input = {
        "notebook_path": str(repo.root / NOTEBOOK),
        "cell_id": "c1",
        "new_source": "fees.sum(axis=1)",
        "edit_mode": "replace",
    }
    payload = repo.tool_payload("NotebookEdit", tool_input, event=EventName.POST_TOOL_USE)

    report = repo.simulate(payload, deps(), event=EventName.POST_TOOL_USE, state=state)

    assert context(report) == [_line("ml-data")]


def test_file_matching_no_skill_is_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    report = edit(repo, deps(), "README.md", state=state)

    assert report.trace.combined.decision is Decision.NONE


def test_out_of_repo_path_is_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, tmp_path: Path
) -> None:
    """Outside the repo the key is the absolute path, which ``**/*.py`` would match."""
    outside = tmp_path / "elsewhere" / "app.py"

    report = edit(repo, deps(), str(outside), state=state)

    assert report.trace.combined.decision is Decision.NONE


def test_stateless_store_is_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    """Regression: stateless, ``once`` always answers True, so the line would repeat per edit."""
    state.mkdir()
    (state / STATE_DIR_NAME).write_text("not a directory\n", encoding="utf-8")

    reports = [edit(repo, deps(), APP, state=state) for _ in range(2)]

    assert [r.trace.combined.decision for r in reports] == [Decision.NONE, Decision.NONE]


@pytest.mark.parametrize(
    "skills",
    [
        "python-coding",
        [{"id": "python-coding"}],
        [{"id": "python-coding", "globs": "**/*.py"}],
        [{"id": 3, "globs": ["**/*.py"]}],
        [{"id": "python-coding", "globs": ["[z-a].py", "**/*.py"]}],
        ["python-coding"],
    ],
    ids=["not-a-list", "no-globs", "globs-not-a-list", "id-not-a-string", "bad-class", "row"],
)
def test_malformed_skills_table_is_silent(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, skills: object
) -> None:
    pack_repo.install_pack([HOOK_ID], handler_config={HOOK_ID: {"skills": skills}})

    report = edit(pack_repo, deps(), APP, state=state)

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.wire.exit_code == 0


def test_malformed_row_does_not_hide_the_valid_ones(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    skills = [{"id": "broken", "globs": ["[z-a].py"]}, {"id": "python-coding", "globs": ["*.py"]}]
    pack_repo.install_pack([HOOK_ID], handler_config={HOOK_ID: {"skills": skills}})

    report = edit(pack_repo, deps(), APP, state=state)

    assert context(report) == [_line("python-coding")]


def test_line_is_at_most_200_characters(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path
) -> None:
    long_id = "s" * 300
    skills = [{"id": long_id, "globs": ["**/*.py"]}]
    pack_repo.install_pack([HOOK_ID], handler_config={HOOK_ID: {"skills": skills}})

    [line] = context(edit(pack_repo, deps(), APP, state=state))

    assert len(line) == 200
    assert line == f"Conventions for this file: skill {long_id}"[:200]


def test_nudge_line_comes_before_lint_feedback(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], state: Path, ruff_program: Path
) -> None:
    """Priority 30 runs ahead of the ruff hooks (50-60), so the event cap never cuts it."""
    head = "def run():\n    return 1\n"
    pack_repo.write("pyproject.toml", '[tool.ruff.lint]\nselect = ["F"]\n')
    pack_repo.write(APP, head + "try:\n    run()\nexcept:\n    raise\n")
    pack_repo.install_pack([HOOK_ID, LINT_HOOK_ID], rules=_reference_probe_rules())
    pin_ruff(pack_repo, ruff_program)
    ruff = FakeRuff(diagnostics=[ruff_row("E722", 5, "Do not use bare `except`")])

    report = edit(pack_repo, deps(proc=ruff, git=head_git(head, APP)), APP, state=state)

    assert context(report) == [
        *SOURCE_LINES,
        'rule python-error-handling (skill python-coding): "src/app.py:5 E722 Do not use bare '
        '`except`"',
    ]


@pytest.mark.parametrize(
    ("harness", "case"), [("claude_code", "skn_edit_app"), ("opencode", "skn_write_app")]
)
def test_claude_and_opencode_payloads_carry_the_nudge(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    hook_payload: Payload,
    state: Path,
    harness: str,
    case: str,
) -> None:
    golden = hook_payload(harness, "post_tool_use", case)

    report = repo.simulate(
        repo.relocate(golden),
        deps(),
        harness=Harness(harness),
        event=EventName.POST_TOOL_USE,
        state=state,
    )

    combined, expected = report.trace.combined, golden.expected["result"]
    assert (combined.decision.value, list(combined.context)) == (
        expected["decision"],
        expected["context"],
    )
    assert list(combined.context) == SOURCE_LINES
    assert report.trace.wire == golden.wire()


def test_sync_derives_the_glob_table_from_the_rendered_member_rules(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """Only rules that pass ``applies_if`` reach the table: no pytest, no FastAPI, no ML here.

    python-tooling still appears, with the globs of its ungated members (Python files,
    stubs and the ruff, mypy, pyright and pre-commit config files).
    """
    (tmp_path / "repo").mkdir()
    repo = make_synthetic_repo(tmp_path / "repo", config_text=CONFIG + "[hooks]\nenabled = true\n")

    rc = _sync.execute(repo, git=FakeGitClient(), hook_deps=hook_deps(tmp_path / "state"))

    hooks = json.loads((repo / GUARD_CONFIG).read_bytes())["hooks"]
    config = hooks[HOOK_ID]["handlers"]["post_tool_use"]["config"]
    assert rc == 0
    assert config == {
        "skills": [
            {"id": "design-patterns", "globs": ["**/*.py"]},
            {"id": "python-architecture", "globs": ARCHITECTURE_GLOBS},
            {"id": "python-coding", "globs": ["**/*.py"]},
            # A repo with neither pytest nor uv: python-tooling's ungated members' globs.
            {"id": "python-tooling", "globs": list(UNGATED_GLOBS)},
        ]
    }


def test_a_consumer_cannot_set_the_skills_table(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """The empty ``CONFIG_SCHEMA`` (H13): the table is sync's alone."""
    table = '[hooks]\nenabled = true\n\n[hooks.skill-nudge]\nskills = ["rogue"]\n'
    repo = make_synthetic_repo(tmp_path, config_text=CONFIG + table)

    rc = _validate.run(argparse.Namespace(repo_root=str(repo)))

    assert rc == 1
    expected = (
        "[hooks.skill-nudge] skills: not a config key of handler 'skill_nudge'; allowed: none"
    )
    assert expected in capsys.readouterr().out


def test_hook_md_matches_its_pack_row_and_handler(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """8.5.1, 12.2: default feedback hook, post_tool_use on edit, write and notebook_edit."""
    hook = engine_hook(HOOK_ID)
    fm = hook.frontmatter

    rc = _validate.run(argparse.Namespace(repo_root=str(tmp_path)))

    assert (fm.tier, fm.priority, fm.events, fm.decisions, fm.on_error) == (
        "default",
        30,
        ["post_tool_use"],
        ["context", "none"],
        "open",
    )
    assert fm.matcher["post_tool_use"].tools == ["edit", "write", "notebook_edit"]
    assert fm.matcher["post_tool_use"].paths == []
    assert fm.handler is not None and fm.handler.builtin == "skill_nudge"
    assert fm.handler.config == {}
    assert (fm.supports, fm.applies_if, fm.linked_rule) == (["claude_code", "opencode"], {}, None)
    assert hook.body.strip() == ""
    assert rc == 0
    assert HOOK_ID not in capsys.readouterr().err
