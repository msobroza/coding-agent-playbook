"""Tests for ``playbook eval --list/--show`` and the bare ``<id>`` path (SPEC §12.8).

The read-only Tier 0 surface. Without ``--run``, bare ``playbook eval <id>``
exits 0 and prints how to run the sample (``tests/cli/test_eval_run.py`` covers
``--run`` itself).
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.commands import eval as _eval

if TYPE_CHECKING:
    from pathlib import Path

#: The repo-local samples :func:`_seed_eval_repo` adds to the core tasks.
_LOCAL_REFACTOR = "refactor/local-extract-helper"
_LOCAL_HAPPY = "generate-tests/local-happy-path"
_LOCAL_EDGE = "generate-tests/local-edge-cases"


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
    """Build a synthetic repo with three prompts and three eval samples.

    Prompt-sample topology mirrors the SPEC §12.8 example:

    - refactor               (1 local sample)  refactor/local-extract-helper
    - generate-tests         (2 local samples) generate-tests/local-happy-path,
                                               generate-tests/local-edge-cases
    - local-only-no-samples    (0 samples) triggers "consider adding samples"

    The "no-samples" prompt uses a non-colliding id so it remains genuinely
    sample-less even after PR 13's engine content (which ships samples for the
    ``review``/``refactor``/``generate-tests`` prompt ids) is layered in.
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
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )
    (prompts_dir / "local-only-no-samples.md").write_text(
        "---\n"
        "id: local-only-no-samples\n"
        "name: Local Only No Samples\n"
        "description: A repo-local prompt deliberately shipped without any eval samples\n"
        "slash: local-only-no-samples\n"
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )

    samples_root = repo / "playbook" / "eval_samples"
    rubric_happy = (
        "[rubric]\n"
        'expr = "quality"\n'
        "[rubric.bind]\n"
        "quality = { fail = 0.5, rubric = [\n"
        '  { judge = "Tests use pytest.parametrize", weight = 0.2 },\n'
        '  { judge = "Test file mirrors layout", weight = 0.2 },\n'
        '  { judge = "All branches covered", weight = 0.4 },\n'
        '  { judge = "No mocking is used", weight = 0.2 },\n'
        "] }\n"
    )
    rubric_edge = (
        "[rubric]\n"
        'expr = "quality"\n'
        "[rubric.bind]\n"
        "quality = { fail = 0.5, rubric = [\n"
        '  { judge = "Empty input is tested", weight = 0.34 },\n'
        '  { judge = "Negative numbers handled", weight = 0.33 },\n'
        '  { judge = "Boundary values listed", weight = 0.33 },\n'
        "] }\n"
    )
    rubric_refactor = (
        "[rubric]\n"
        'expr = "quality"\n'
        "[rubric.bind]\n"
        'quality = { fail = 0.5, rubric = [{ judge = "Helper has tests", weight = 1.0 }] }\n'
    )

    # Repo-local samples join the core tasks under names core does not use.
    for sample_id, description, rubric_block in [
        (
            _LOCAL_REFACTOR,
            "Extract a helper function and update call sites",
            rubric_refactor,
        ),
        (
            _LOCAL_HAPPY,
            "Generate tests for a simple pure function with no edge cases",
            rubric_happy,
        ),
        (
            _LOCAL_EDGE,
            "Cover the gnarly edge cases for the same function",
            rubric_edge,
        ),
    ]:
        d = samples_root / sample_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "setup").mkdir(exist_ok=True)
        (d / "sample.toml").write_text(
            f'id = "{sample_id}"\n'
            f'description = "{description}"\n'
            "\n"
            "[setup]\n"
            "files = []\n"
            'project_kind = "python-application"\n'
            "\n"
            "[invocation]\n"
            'prompt_args = "for some target"\n'
            "\n"
            "[gate]\n"
            'expr = "created and contains"\n'
            "[gate.bind]\n"
            'created = { check = "file_exists", path = "tests/test_x.py" }\n'
            'contains = { check = "file_contains", path = "tests/test_x.py", pattern = "def test_" }\n'
            "\n" + rubric_block + "\n"
            "[verdict]\n"
            'trial = "gate and rubric"\n',
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
    assert "local-only-no-samples" in out
    # Tree markers from SPEC §12.8.
    assert "├──" in out or "└──" in out
    # Every sample name appears.
    assert _LOCAL_HAPPY in out
    assert _LOCAL_EDGE in out
    assert _LOCAL_REFACTOR in out
    # Sample-defined marker for prompts that have samples.
    assert "sample defined" in out
    # Warning for the sample-less prompt — scope the assertion to that prompt's
    # tree segment so engine-shipped prompts with samples don't crowd it out.
    local_only_idx = out.index("local-only-no-samples")
    # The synthetic prompt's tree segment runs from its header to the next
    # blank line (or the Total: footer); within that window the warning must
    # appear.
    segment_end = out.find("\n\n", local_only_idx)
    if segment_end == -1:
        segment_end = out.index("Total:")
    segment = out[local_only_idx:segment_end]
    assert "consider adding samples" in segment
    # Per-sample summary line shape.
    assert "rubric criteria" in out
    assert "gate checks" in out
    # Final tally.
    assert "Total" in out


def test_eval_list_groups_samples_under_prompts(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    _eval.run(_ns(tmp_path, list_=True))
    out = capsys.readouterr().out
    idx_header = out.index("generate-tests")
    idx_happy = out.index(_LOCAL_HAPPY)
    idx_edge = out.index(_LOCAL_EDGE)
    # #281: samples list alphabetically by id under their prompt, not in declared order
    assert idx_header < idx_edge < idx_happy


def test_plural_helper_uses_singular_for_n_equals_one():
    """Unit test for the ``_plural`` helper: it must render ``1 prompt`` (not
    ``1 prompts``) and append ``s`` for any other count. SPEC §12.8 shows both
    shapes.

    Exercises the n=1 branch directly because integration via
    ``playbook eval --list`` can't reach n=1 on a real repo: the engine ships four
    prompts (PR 13) so the prompt count is never 1 in practice.
    """
    from coding_agent_playbook.commands._eval_enumerate import _plural

    assert _plural(0, "prompt") == "0 prompts"
    assert _plural(1, "prompt") == "1 prompt"
    assert _plural(2, "prompt") == "2 prompts"
    assert _plural(1, "eval sample") == "1 eval sample"
    assert _plural(3, "eval sample") == "3 eval samples"


def test_eval_list_total_pluralizes_prompts_without_samples_correctly(
    tmp_path, make_synthetic_repo, capsys
):
    """The ``prompts without samples`` suffix has to be pluralised separately
    because the head noun isn't at the tail of the phrase (naively appending
    ``s`` would emit ``prompt without taskss``).

    Singular case: seed a repo with exactly one sample-less repo-local prompt.
    The Total: line must read ``1 prompt without samples``, never ``1 prompts
    without samples``. The other Total: counts include the engine's prompts and
    samples so we only pin the suffix here.
    """
    make_synthetic_repo(tmp_path)
    prompts_dir = tmp_path / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    # Non-colliding id so the engine doesn't ship samples for it.
    (prompts_dir / "lone-no-samples.md").write_text(
        "---\n"
        "id: lone-no-samples\n"
        "name: Lone No Samples\n"
        "description: A prompt with deliberately zero eval samples\n"
        "slash: lone-no-samples\n"
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )

    _eval.run(_ns(tmp_path, list_=True))
    out = capsys.readouterr().out
    assert "1 prompt without samples" in out
    # Negative assertion for the buggy plural-only form.
    assert "1 prompts without samples" not in out


def test_eval_show_existing_sample_prints_details(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, show=_LOCAL_HAPPY))
    assert rc == 0
    out = capsys.readouterr().out
    assert f"Sample: {_LOCAL_HAPPY}" in out
    assert "Source:" in out
    assert "Prompt under test: generate-tests" in out
    assert "Description:" in out
    assert "Setup:" in out
    assert "Invocation:" in out
    assert "Gate" in out
    assert "Rubric" in out
    assert "Verdict:" in out
    # Numeric metadata exposed.
    assert "4 criteria" in out
    # Per-criterion weighted listing.
    assert "0.4" in out


def test_show_uses_prompt_slash_not_id_when_they_differ(tmp_path, make_synthetic_repo, capsys):
    """When ``prompt.slash`` differs from ``prompt.id`` (allowed by the
    canonical Prompt schema), ``playbook eval --show`` must print the slash in the
    ``Prompt: /...`` line, not the id.

    Regression: PR 11 originally used ``sample.prompt_id`` as the slash because
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
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )
    sample_dir = tmp_path / "playbook" / "eval_samples" / _LOCAL_HAPPY
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "sample.toml").write_text(
        f'id = "{_LOCAL_HAPPY}"\n'
        'description = "Tests for a simple function"\n'
        "[setup]\n"
        "files = []\n"
        'project_kind = "python-application"\n'
        "[invocation]\n"
        'prompt_args = "target"\n',
        encoding="utf-8",
    )

    rc = _eval.run(_ns(tmp_path, show=_LOCAL_HAPPY))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Prompt: /gen-tests" in out
    # The line that prints the slash must NOT use the id when they differ.
    assert "Prompt: /generate-tests" not in out


def test_display_source_path_uses_package_prefix_for_engine_samples(tmp_path):
    """A bundled layer's sample is labelled ``<package>/eval_samples/<dir>/``.

    The label comes from the layer, not from the path: even a bundled sample whose
    path holds ``resources/eval_samples/`` gets no ``resources/`` in its label."""
    from coding_agent_playbook.commands._eval_enumerate import _display_source_path
    from coding_agent_playbook.evals.sample import EvalSample

    # Synthesize an engine sample under the pre-v0.19 layout
    # (<package>/resources/eval_samples/<id>/sample.toml), so only the layer can
    # explain a label without ``resources/``.
    sample_dir = (
        tmp_path
        / "coding_agent_playbook"
        / "resources"
        / "eval_samples"
        / "some-prompt"
        / "sample-a"
    )
    sample_dir.mkdir(parents=True)
    sample = EvalSample(
        id="sample-a",
        prompt_id="some-prompt",
        description="desc",
        source_path=sample_dir / "sample.toml",
        source_package="coding_agent_playbook",
    )
    assert (
        _display_source_path(sample) == "coding_agent_playbook/eval_samples/some-prompt/sample-a/"
    )


def test_display_source_path_uses_package_prefix_for_overlay_samples(tmp_path):
    """A third-party overlay keeps its real package-relative path,
    ``<package>/resources/eval_samples/<dir>/``."""
    from coding_agent_playbook.commands._eval_enumerate import _display_source_path
    from coding_agent_playbook.evals.sample import EvalSample

    sample_dir = (
        tmp_path / "playbook_rules_bnp" / "resources" / "eval_samples" / "pii-scan" / "basic"
    )
    sample_dir.mkdir(parents=True)
    sample = EvalSample(
        id="pii-scan",
        prompt_id="pii-scan",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package="playbook_rules_bnp",
    )
    assert (
        _display_source_path(sample) == "playbook_rules_bnp/resources/eval_samples/pii-scan/basic/"
    )


@pytest.mark.parametrize(
    ("source_package", "sample_dir_parts", "expected"),
    [
        (
            "coding_agent_playbook.plugins.x",
            ("catalog", "plugins", "x", "eval_samples", "p", "t"),
            "coding_agent_playbook.plugins.x/eval_samples/p/t/",
        ),
        (
            "some_overlay",
            ("weird_root", "p", "sample-x"),
            "some_overlay/resources/eval_samples/p/sample-x/",
        ),
        ("<repo-local>", ("no_playbook_dir", "p", "sample-y"), "playbook/eval_samples/p/sample-y/"),
    ],
    ids=["bundled-plugin", "overlay-odd-layout", "repo-local-odd-layout"],
)
def test_display_source_path_depends_only_on_layer_and_dir(
    tmp_path: Path, source_package: str, sample_dir_parts: tuple[str, ...], expected: str
) -> None:
    """The label is built from the layer kind and the sample dir's name alone.

    No segment of the path is searched for, so an unusual parent layout
    (no ``resources/``, no ``playbook/``) still yields the canonical label."""
    from coding_agent_playbook.commands._eval_enumerate import _display_source_path
    from coding_agent_playbook.evals.sample import EvalSample

    sample_dir = tmp_path.joinpath(*sample_dir_parts)
    sample = EvalSample(
        id=sample_dir.name,
        prompt_id="p",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package=source_package,
    )
    assert _display_source_path(sample) == expected


@pytest.mark.parametrize(
    ("source_package", "expected"),
    [
        ("coding_agent_playbook", "coding_agent_playbook/eval_samples/p/sample-dir/"),
        ("some_overlay", "some_overlay/resources/eval_samples/p/sample-dir/"),
        ("<repo-local>", "playbook/eval_samples/p/sample-dir/"),
    ],
    ids=["bundled", "overlay", "repo-local"],
)
def test_display_source_path_uses_directory_not_sample_id(
    tmp_path: Path, source_package: str, expected: str
) -> None:
    """``<dir>`` is the sample directory's name; nothing ties ``sample.id`` to it."""
    from coding_agent_playbook.commands._eval_enumerate import _display_source_path
    from coding_agent_playbook.evals.sample import EvalSample

    sample_dir = tmp_path / "eval_samples" / "p" / "sample-dir"
    sample = EvalSample(
        id="declared-id",
        prompt_id="p",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package=source_package,
    )
    assert _display_source_path(sample) == expected


def test_show_source_path_is_repo_relative_for_repo_local_samples(
    tmp_path, make_synthetic_repo, capsys
):
    """``playbook eval --show``'s ``Source:`` line for a repo-local sample must start
    at ``playbook/eval_samples/...``, not an absolute filesystem path.

    SPEC §12.8 example uses package-relative paths
    (``coding_agent_playbook/eval_samples/.../``); the repo-local
    analogue should anchor at ``playbook/`` so the output is reproducible
    across user machines (no leak of ``$HOME``/scratch-dir layouts).

    Uses a non-colliding sample id so the engine's PR 13 samples (which include
    ``generate-tests-happy-path``) don't shadow the repo-local copy in the
    by-id lookup.
    """
    make_synthetic_repo(tmp_path)
    # Author a prompt + sample with non-colliding ids so the engine's PR 13
    # eval samples don't shadow the repo-local copy.
    prompts_dir = tmp_path / "playbook" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "local-only.md").write_text(
        "---\n"
        "id: local-only\n"
        "name: Local Only\n"
        "description: A repo-local-only prompt for path-display assertions\n"
        "slash: local-only\n"
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )
    sample_dir = tmp_path / "playbook" / "eval_samples" / "local-only" / "unique-zzz"
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "sample.toml").write_text(
        'id = "local-only/unique-zzz"\n'
        'description = "Repo-local sample that doesn\'t collide with engine ids"\n'
        "[setup]\n"
        "files = []\n"
        'project_kind = "python-application"\n'
        "[invocation]\n"
        'prompt_args = ""\n',
        encoding="utf-8",
    )
    rc = _eval.run(_ns(tmp_path, show="local-only/unique-zzz"))
    assert rc == 0
    out = capsys.readouterr().out
    # The Source: line must read the repo-relative form, not the absolute
    # path under tmp_path.
    assert "Source: playbook/eval_samples/local-only/unique-zzz/" in out
    assert str(tmp_path) not in out


def test_a_task_directory_naming_no_prompt_is_an_error(tmp_path, make_synthetic_repo, capsys):
    """The task registry refuses a task whose prompt does not exist (#302), naming its directory."""
    make_synthetic_repo(tmp_path)
    # No prompt file at all — only the sample.
    sample_dir = tmp_path / "playbook" / "eval_samples" / "missing-prompt" / "orphan-sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "sample.toml").write_text(
        'id = "missing-prompt/orphan-sample"\n'
        'description = "Sample without a prompt"\n'
        "[setup]\n"
        "files = []\n"
        'project_kind = "python-application"\n'
        "[invocation]\n"
        'prompt_args = ""\n',
        encoding="utf-8",
    )

    rc = _eval.run(_ns(tmp_path, show="missing-prompt/orphan-sample"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "eval_samples/missing-prompt: task directory names no prompt" in err


def test_eval_bare_task_lists_its_samples_and_how_to_run_them(
    tmp_path, make_synthetic_repo, capsys
):
    """``playbook eval <task>`` selects every sample of the task, core and repo-local."""
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, id_="generate-tests"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Task generate-tests has 5 eval samples:" in out
    assert f"  {_LOCAL_EDGE}\n" in out
    assert "  generate-tests/happy-path\n" in out
    assert "playbook eval generate-tests --run --runner fake" in out


def test_eval_unknown_task_lists_the_known_tasks(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, id_="revue"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "no task 'revue'; known tasks:" in err
    assert "generate-tests" in err


def test_eval_show_unknown_id_exits_nonzero(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, show="does-not-exist"))
    assert rc == 1
    err = capsys.readouterr()
    combined = err.out + err.err
    assert "does-not-exist" in combined
    assert "no eval sample" in combined.lower()


def test_eval_bare_id_known_sample_exits_zero_with_run_hint(tmp_path, make_synthetic_repo, capsys):
    """Without ``--run`` a known sample prints how to run it (the runner is live)."""
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, id_=_LOCAL_HAPPY))
    assert rc == 0
    out = capsys.readouterr().out
    assert "not yet implemented" not in out
    assert f"playbook eval {_LOCAL_HAPPY} --run --runner fake" in out
    assert "--judge llm" in out


def test_eval_bare_id_unknown_sample_exits_nonzero(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, id_="ghost-sample"))
    assert rc == 1
    err = capsys.readouterr()
    combined = err.out + err.err
    assert "ghost-sample" in combined


def test_eval_no_args_defaults_to_list(tmp_path, make_synthetic_repo, capsys):
    _seed_eval_repo(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Eval samples" in out or "generate-tests" in out


def test_eval_list_handles_repo_with_no_local_artifacts(tmp_path, make_synthetic_repo, capsys):
    """``playbook eval --list`` on a fresh repo with no repo-local prompts or samples
    must:

    - still print the SPEC §12.8 header ``=== Eval samples ===``
    - print a ``Total: ... prompts, ... eval samples, ... prompts without
      samples`` summary (with the engine-shipped totals — PR 13 ships 4
      prompts and 8 eval samples)
    - exit 0 (no error — a repo with no local artifacts is a legitimate
      state; engine content is still listed)
    - not emit any repo-local prompts/samples since none were authored
    """
    # Bare synthetic repo: pyproject + config, no repo-local prompts or samples.
    make_synthetic_repo(tmp_path)
    rc = _eval.run(_ns(tmp_path, list_=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== Eval samples ===" in out
    # Total: line present — exact counts come from the engine.
    assert "Total:" in out
    assert "eval sample" in out
    # No repo-local prompts or samples since the synthetic repo authored none.
    assert "(repo-local)" not in out
