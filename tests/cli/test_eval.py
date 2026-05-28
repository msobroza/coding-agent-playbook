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


def test_eval_list_total_pluralizes_correctly(tmp_path, make_synthetic_repo, capsys):
    """The ``Total:`` line must use singular ``prompt``/``eval task``/``prompt
    without tasks`` when the count is exactly 1, plural otherwise. SPEC §12.8
    shows both shapes."""
    # Seed a repo with exactly one prompt, one task, zero prompts-without-tasks
    # to exercise the n=1 branch on the first two counts and the n=0 branch
    # on the third.
    make_synthetic_repo(tmp_path)
    prompts_dir = tmp_path / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "solo.md").write_text(
        "---\n"
        "id: solo\n"
        "name: Solo\n"
        "description: Lonely prompt\n"
        "slash: solo\n"
        "eval_tasks:\n"
        "  - solo-task\n"
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )
    task_dir = tmp_path / "playbook" / "eval_tasks" / "solo-task"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(
        'id = "solo-task"\n'
        'prompt_id = "solo"\n'
        'description = "Only task"\n'
        "[setup]\n"
        "files = []\n"
        'project_kind = "python-application"\n'
        'python_version = "3.12"\n'
        "frameworks = []\n"
        "[invocation]\n"
        'prompt_args = ""\n',
        encoding="utf-8",
    )

    _eval.run(_ns(tmp_path, list_=True))
    out = capsys.readouterr().out
    assert "Total: 1 prompt, 1 eval task, 0 prompts without tasks" in out
    # Negative assertions for the buggy plural-only form.
    assert "1 prompts" not in out
    assert "1 eval tasks" not in out


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


def test_display_source_path_uses_package_prefix_for_engine_tasks(tmp_path):
    """The ``_display_source_path`` helper renders engine/overlay tasks as
    ``<package>/resources/eval_tasks/<id>/`` (the canonical SPEC §12.8 form).

    Unit-level test because the engine ships zero tasks in v1, so no
    integration test through ``cap eval --show`` exercises this branch."""
    from coding_agent_playbook.commands.eval import _display_source_path
    from coding_agent_playbook.evals.task import EvalTask

    # Synthesize a task that looks like it came from importlib.resources
    # (typical layout: <package>/resources/eval_tasks/<id>/task.toml).
    task_dir = tmp_path / "coding_agent_playbook" / "resources" / "eval_tasks" / "task-a"
    task_dir.mkdir(parents=True)
    task = EvalTask(
        id="task-a",
        prompt_id="some-prompt",
        description="desc",
        source_path=task_dir / "task.toml",
        source_package="coding_agent_playbook",
    )
    assert _display_source_path(task) == "coding_agent_playbook/resources/eval_tasks/task-a/"


def test_display_source_path_uses_package_prefix_for_overlay_tasks(tmp_path):
    """Overlay packages get the same treatment, with the overlay's name as
    the prefix instead of the engine's."""
    from coding_agent_playbook.commands.eval import _display_source_path
    from coding_agent_playbook.evals.task import EvalTask

    task_dir = tmp_path / "playbook_rules_bnp" / "resources" / "eval_tasks" / "pii-scan"
    task_dir.mkdir(parents=True)
    task = EvalTask(
        id="pii-scan",
        prompt_id="pii-scan",
        description="d",
        source_path=task_dir / "task.toml",
        source_package="playbook_rules_bnp",
    )
    assert _display_source_path(task) == "playbook_rules_bnp/resources/eval_tasks/pii-scan/"


def test_display_source_path_falls_back_gracefully_for_unusual_paths(tmp_path):
    """If the path doesn't contain the expected segment (``resources`` for
    engine/overlay; ``playbook`` for repo-local), the helper falls back to
    the directory basename so the line is still attributable but doesn't
    crash."""
    from coding_agent_playbook.commands.eval import _display_source_path
    from coding_agent_playbook.evals.task import EvalTask

    # No "resources" segment in the path.
    weird = tmp_path / "weird_root" / "task-x"
    weird.mkdir(parents=True)
    task = EvalTask(
        id="task-x",
        prompt_id="p",
        description="d",
        source_path=weird / "task.toml",
        source_package="some_overlay",
    )
    # Falls back to <package>/<basename>/ — still meaningful.
    assert _display_source_path(task) == "some_overlay/task-x/"

    # No "playbook" segment for repo-local — also doesn't crash.
    weird2 = tmp_path / "no_playbook_dir" / "task-y"
    weird2.mkdir(parents=True)
    task2 = EvalTask(
        id="task-y",
        prompt_id="p",
        description="d",
        source_path=weird2 / "task.toml",
        source_package="<repo-local>",
    )
    assert _display_source_path(task2) == "task-y/"


def test_show_source_path_is_repo_relative_for_repo_local_tasks(
    tmp_path, make_synthetic_repo, capsys
):
    """``cap eval --show``'s ``Source:`` line for a repo-local task must start
    at ``playbook/eval_tasks/...``, not an absolute filesystem path.

    SPEC §12.8 example uses package-relative paths
    (``coding_agent_playbook/resources/eval_tasks/.../``); the repo-local
    analogue should anchor at ``playbook/`` so the output is reproducible
    across user machines (no leak of ``$HOME``/scratch-dir layouts)."""
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, show="generate-tests-happy-path"))
    assert rc == 0
    out = capsys.readouterr().out
    # The Source: line must read the repo-relative form, not the absolute
    # path under tmp_path.
    assert "Source: playbook/eval_tasks/generate-tests-happy-path/" in out
    assert str(tmp_path) not in out


def test_show_falls_back_to_prompt_id_when_prompt_missing(tmp_path, make_synthetic_repo, capsys):
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
        "frameworks = []\n"
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


def test_eval_list_handles_empty_repo(tmp_path, make_synthetic_repo, capsys):
    """``cap eval --list`` on a fresh repo with zero prompts and zero tasks
    must:

    - still print the SPEC §12.8 header ``=== Eval tasks ===``
    - print the ``Total: 0 prompts, 0 eval tasks, 0 prompts without tasks``
      summary
    - exit 0 (no error — an empty playbook is a legitimate state)
    - not emit any tree characters (``├──`` / ``└──``) since there's no
      tree to draw
    - not emit a stray blank line between the header and the Total
    """
    # Bare synthetic repo: pyproject + config, no prompts, no eval tasks.
    make_synthetic_repo(tmp_path)
    rc = _eval.run(_ns(tmp_path, list_=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== Eval tasks ===" in out
    assert "Total: 0 prompts, 0 eval tasks, 0 prompts without tasks" in out
    # No stray tree characters on an empty listing.
    assert "├──" not in out
    assert "└──" not in out
    # No stray blank line between the header and the Total line.
    assert "=== Eval tasks ===\n\nTotal:" not in out
    # The output should be exactly two lines (header + total), plus the
    # trailing newline from print().
    assert out.strip().count("\n") == 1
