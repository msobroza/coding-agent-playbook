"""Tests for ``cap eval --list/--show`` and the bare ``<id>`` runner-deferred
path (SPEC §12.8 / §15).

PR 11 turns the PR-10 deferral stub into the real Tier 0 read-only surface.
The runner remains absent; bare ``cap eval <id>`` exits 0 with a deferral
message that references SPEC §15.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.commands import eval as _eval

if TYPE_CHECKING:
    from pathlib import Path


def _ns(
    repo: Path,
    *,
    list_: bool = False,
    show: str | None = None,
    id_: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        repo_root=str(repo),
        list=list_,
        show=show,
        id=id_,
    )


def _seed_eval_repo(repo: Path, make_synthetic_repo: Any) -> None:
    """Build a synthetic repo with three prompts and three eval tasks.

    Prompt-task topology mirrors the SPEC §12.8 example:

    - refactor               (1 task)  refactor-extract-helper
    - generate-tests         (2 tasks) generate-tests-happy-path,
                                       generate-tests-edge-cases
    - review                 (0 tasks) triggers "consider adding tasks"
    """
    make_synthetic_repo(repo)
    prompts_dir = repo / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    (prompts_dir / "refactor.md").write_text(
        "---\n"
        "id: refactor\n"
        "name: Refactor\n"
        "description: Refactor an existing function\n"
        "slash: refactor\n"
        "eval_tasks:\n"
        "  - refactor-extract-helper\n"
        "---\n"
        "Refactor body.\n",
        encoding="utf-8",
    )
    (prompts_dir / "generate-tests.md").write_text(
        "---\n"
        "id: generate-tests\n"
        "name: Generate Tests\n"
        "description: Generate pytest tests for a function\n"
        "slash: generate-tests\n"
        "eval_tasks:\n"
        "  - generate-tests-happy-path\n"
        "  - generate-tests-edge-cases\n"
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )
    (prompts_dir / "review.md").write_text(
        "---\n"
        "id: review\n"
        "name: Review\n"
        "description: Review a code change\n"
        "slash: review\n"
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )

    tasks_root = repo / "playbook" / "eval_tasks"
    rubric_happy = (
        "criteria = [\n"
        '  "Tests use pytest.parametrize",\n'
        '  "Test file mirrors layout",\n'
        '  "All branches covered",\n'
        '  "No mocking is used",\n'
        "]\n"
        "weights = [0.2, 0.2, 0.4, 0.2]\n"
    )
    rubric_edge = (
        "criteria = [\n"
        '  "Empty input is tested",\n'
        '  "Negative numbers handled",\n'
        '  "Boundary values listed",\n'
        "]\n"
    )
    rubric_refactor = 'criteria = ["Helper has tests"]\nweights = [1.0]\n'

    for task_id, prompt_id, description, rubric_block in [
        (
            "refactor-extract-helper",
            "refactor",
            "Extract a helper function and update call sites",
            rubric_refactor,
        ),
        (
            "generate-tests-happy-path",
            "generate-tests",
            "Generate tests for a simple pure function with no edge cases",
            rubric_happy,
        ),
        (
            "generate-tests-edge-cases",
            "generate-tests",
            "Cover the gnarly edge cases for the same function",
            rubric_edge,
        ),
    ]:
        d = tasks_root / task_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "setup").mkdir(exist_ok=True)
        (d / "task.toml").write_text(
            f'id = "{task_id}"\n'
            f'prompt_id = "{prompt_id}"\n'
            f'description = "{description}"\n'
            "\n"
            "[setup]\n"
            "files = []\n"
            'project_kind = "python-application"\n'
            'python_version = "3.12"\n'
            'frameworks = ["pytest"]\n'
            "\n"
            "[invocation]\n"
            'prompt_args = "for some target"\n'
            "\n"
            "[expected]\n"
            'files_created = ["tests/test_x.py"]\n'
            "files_must_contain = [\n"
            '  { path = "tests/test_x.py", pattern = "def test_" },\n'
            "]\n"
            "\n"
            "[rubric]\n" + rubric_block,
            encoding="utf-8",
        )


def test_eval_list_prints_tree(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, list_=True))
    assert rc == 0
    out = capsys.readouterr().out
    # Each prompt header appears.
    assert "generate-tests" in out
    assert "refactor" in out
    assert "review" in out
    # Tree markers from SPEC §12.8.
    assert "├──" in out or "└──" in out
    # Every task name appears.
    assert "generate-tests-happy-path" in out
    assert "generate-tests-edge-cases" in out
    assert "refactor-extract-helper" in out
    # Task-defined marker for prompts that have tasks.
    assert "task defined" in out
    # Warning for the review prompt which has none.
    assert "consider adding tasks" in out
    # Per-task summary line shape.
    assert "rubric criteria" in out
    assert "programmatic checks" in out
    # Final tally.
    assert "Total" in out


def test_eval_list_groups_tasks_under_prompts(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    _eval.run(_ns(tmp_path, list_=True))
    out = capsys.readouterr().out
    idx_header = out.index("generate-tests")
    idx_happy = out.index("generate-tests-happy-path")
    idx_edge = out.index("generate-tests-edge-cases")
    assert idx_header < idx_happy < idx_edge


def test_eval_show_existing_task_prints_details(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, show="generate-tests-happy-path"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Task: generate-tests-happy-path" in out
    assert "Source:" in out
    assert "Prompt under test: generate-tests" in out
    assert "Description:" in out
    assert "Setup:" in out
    assert "Invocation:" in out
    assert "Expected" in out
    assert "Rubric" in out
    # Numeric metadata exposed.
    assert "4 criteria" in out
    # Per-criterion weighted listing.
    assert "0.4" in out


def test_show_uses_prompt_slash_not_id_when_they_differ(tmp_path, make_synthetic_repo, capsys):
    """When ``prompt.slash`` differs from ``prompt.id`` (allowed by the
    canonical Prompt schema), ``cap eval --show`` must print the slash in the
    ``Prompt: /...`` line, not the id.

    Regression: PR 11 originally used ``task.prompt_id`` as the slash because
    the show-printer didn't have the prompt registry. That broke for any
    prompt whose slash deliberately differed from its id.
    """
    make_synthetic_repo(tmp_path)
    prompts_dir = tmp_path / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    # Prompt id="generate-tests" but slash="gen-tests" (deliberately different).
    (prompts_dir / "generate-tests.md").write_text(
        "---\n"
        "id: generate-tests\n"
        "name: Generate Tests\n"
        "description: Generate pytest tests\n"
        "slash: gen-tests\n"
        "eval_tasks:\n"
        "  - generate-tests-happy-path\n"
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )
    task_dir = tmp_path / "playbook" / "eval_tasks" / "generate-tests-happy-path"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(
        'id = "generate-tests-happy-path"\n'
        'prompt_id = "generate-tests"\n'
        'description = "Tests for a simple function"\n'
        "[setup]\n"
        "files = []\n"
        'project_kind = "python-application"\n'
        'python_version = "3.12"\n'
        'frameworks = ["pytest"]\n'
        "[invocation]\n"
        'prompt_args = "target"\n',
        encoding="utf-8",
    )

    rc = _eval.run(_ns(tmp_path, show="generate-tests-happy-path"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Prompt: /gen-tests" in out
    # The line that prints the slash must NOT use the id when they differ.
    assert "Prompt: /generate-tests" not in out


def test_show_falls_back_to_prompt_id_when_prompt_missing(
    tmp_path, make_synthetic_repo, capsys
):
    """If a task references a prompt that isn't loaded (mid-authoring state),
    ``cap eval --show`` falls back to printing the ``prompt_id`` as the slash
    so the output is still useful."""
    make_synthetic_repo(tmp_path)
    # No prompt file at all — only the task.
    task_dir = tmp_path / "playbook" / "eval_tasks" / "orphan-task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(
        'id = "orphan-task"\n'
        'prompt_id = "missing-prompt"\n'
        'description = "Task without a prompt"\n'
        "[setup]\n"
        "files = []\n"
        'project_kind = "python-application"\n'
        'python_version = "3.12"\n'
        'frameworks = []\n'
        "[invocation]\n"
        'prompt_args = ""\n',
        encoding="utf-8",
    )

    rc = _eval.run(_ns(tmp_path, show="orphan-task"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Prompt: /missing-prompt" in out


def test_eval_show_unknown_id_exits_nonzero(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, show="does-not-exist"))
    assert rc == 1
    err = capsys.readouterr()
    combined = err.out + err.err
    assert "does-not-exist" in combined
    assert "no eval task" in combined.lower()


def test_eval_bare_id_known_task_exits_zero_with_deferral(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, id_="generate-tests-happy-path"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Eval runner not yet implemented" in out
    # SPEC §15 v2 pointer.
    assert "15" in out
    assert "generate-tests-happy-path" in out


def test_eval_bare_id_unknown_task_exits_nonzero(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, id_="ghost-task"))
    assert rc == 1
    err = capsys.readouterr()
    combined = err.out + err.err
    assert "ghost-task" in combined


def test_eval_no_args_defaults_to_list(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Eval tasks" in out or "generate-tests" in out
