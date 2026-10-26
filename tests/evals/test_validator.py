"""Tests for ``coding_agent_playbook.evals.validator`` (C7 compile-based rules).

The schema rules (``[gate]``/``[rubric]``/``[verdict]``) are checked by trial-
compiling the sample; the non-schema rules (setup.files, prompt_id, prompt↔sample
back-references) and a light ``[aggregate]`` shape check are kept. Each rule has a
passing case and a failing case.
"""

from __future__ import annotations

from pathlib import Path

from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.evals.sample import EvalSample, Layer, SampleSetup, Verdict
from coding_agent_playbook.evals.validator import (
    EvalValidationError,
    validate_samples,
)


def _make_prompt(prompt_id: str) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name=prompt_id.title(),
            description="prompt",
            slash=prompt_id,
        ),
        body="body\n",
        template_body="body\n",
        is_templated=False,
        source_path=None,
        source_package="<test>",
    )


def _gate(*, path: str = "x.py") -> Layer:
    """A one-handle gate that compiles cleanly (single-handle default expr)."""
    return Layer(bind={"a": {"check": "file_exists", "path": path}})


def _make_sample(
    *,
    sample_id: str,
    prompt_id: str,
    sample_dir: Path,
    setup_files: list[str] | None = None,
    gate: Layer | None = None,
    rubric: Layer | None = None,
    verdict: str = "gate",
    aggregate: Layer | None = None,
) -> EvalSample:
    return EvalSample(
        id=sample_id,
        prompt_id=prompt_id,
        description="a sample",
        source_path=sample_dir / "sample.toml",
        source_package="<test>",
        setup=SampleSetup(files=[Path(p) for p in (setup_files or [])]),
        gate=gate if gate is not None else _gate(),
        rubric=rubric,
        verdict=Verdict(mode="boolean", trial=verdict),
        aggregate=aggregate,
    )


# Rule 1 / 2: a well-formed sample (clean-compiling schema) passes.
def test_validate_samples_passes_well_formed(tmp_path: Path) -> None:
    sample_dir = tmp_path / "ok-sample"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = _make_sample(sample_id="ok-sample", prompt_id="demo", sample_dir=sample_dir)
    assert validate_samples([sample], [prompt]) == []


# Rule 2 (negative): an unknown check id surfaces as a compile error.
def test_validate_samples_flags_unknown_check(tmp_path: Path) -> None:
    sample_dir = tmp_path / "bad-check"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = _make_sample(
        sample_id="bad-check",
        prompt_id="demo",
        sample_dir=sample_dir,
        gate=Layer(bind={"a": {"check": "no_such_check", "path": "x"}}),
    )
    errors = validate_samples([sample], [prompt])
    assert any("no_such_check" in e.message for e in errors)


# Rule 2 (negative): a gate expr identifier not in the bind table is a compile error.
def test_validate_samples_flags_expr_ident_not_in_bind(tmp_path: Path) -> None:
    sample_dir = tmp_path / "bad-expr"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = _make_sample(
        sample_id="bad-expr",
        prompt_id="demo",
        sample_dir=sample_dir,
        gate=Layer(bind={"a": {"check": "file_exists", "path": "x"}}, expr="a and ghost"),
    )
    errors = validate_samples([sample], [prompt])
    assert any("ghost" in e.message for e in errors)


# Rule 2 (negative): a verdict naming an absent layer is a compile error.
def test_validate_samples_flags_verdict_missing_layer(tmp_path: Path) -> None:
    sample_dir = tmp_path / "bad-verdict"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    # Default verdict mentions 'rubric' but there is no [rubric] block.
    sample = _make_sample(
        sample_id="bad-verdict",
        prompt_id="demo",
        sample_dir=sample_dir,
        verdict="gate and rubric",
    )
    errors = validate_samples([sample], [prompt])
    assert any("rubric" in e.message for e in errors)


# Rule 2 (negative): a rubric group whose weights don't sum to 1.0 is a compile error.
def test_validate_samples_flags_rubric_weight_sum(tmp_path: Path) -> None:
    sample_dir = tmp_path / "bad-weights"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = _make_sample(
        sample_id="bad-weights",
        prompt_id="demo",
        sample_dir=sample_dir,
        rubric=Layer(
            bind={
                "q": {
                    "fail": 0.5,
                    "rubric": [{"judge": "a", "weight": 0.3}, {"judge": "b", "weight": 0.3}],
                }
            }
        ),
        verdict="gate and rubric",
    )
    errors = validate_samples([sample], [prompt])
    assert any("weight" in e.message.lower() and "sum" in e.message.lower() for e in errors)


# Rule 2 (negative): weighted [verdict] referencing an absent layer is a compile error (C10).
def test_validate_samples_flags_weighted_verdict_unknown_layer(tmp_path: Path) -> None:
    sample_dir = tmp_path / "bad-weighted"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = EvalSample(
        id="bad-weighted",
        prompt_id="demo",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package="<test>",
        setup=SampleSetup(),
        gate=_gate(),
        # No [rubric] block, yet weights name it.
        verdict=Verdict(
            mode="weighted",
            weights={"gate": 0.4, "rubric": 0.6},
            fail=0.5,
        ),
    )
    errors = validate_samples([sample], [prompt])
    assert any("unknown layer" in e.message for e in errors)


# Rule 2 (negative): a sample with no layer at all cannot compile.
def test_validate_samples_flags_no_layer(tmp_path: Path) -> None:
    sample_dir = tmp_path / "no-layer"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = EvalSample(
        id="no-layer",
        prompt_id="demo",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package="<test>",
        setup=SampleSetup(),
        gate=None,
        rubric=None,
        verdict=Verdict(mode="boolean", trial="gate"),
    )
    errors = validate_samples([sample], [prompt])
    assert any("at least one" in e.message for e in errors)


# Rule 3 (positive): a well-formed [aggregate] passes.
def test_validate_samples_accepts_valid_aggregate(tmp_path: Path) -> None:
    sample_dir = tmp_path / "agg-ok"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = _make_sample(
        sample_id="agg-ok",
        prompt_id="demo",
        sample_dir=sample_dir,
        aggregate=Layer(bind={"r": {"metric": "pass_at_k", "k": 3, "over": "verdict"}}),
    )
    errors = validate_samples([sample], [prompt])
    assert [e for e in errors if "aggregate" in e.message.lower()] == []


# Rule 3 (negative): a bad aggregate metric / k / over is flagged.
def test_validate_samples_flags_bad_aggregate(tmp_path: Path) -> None:
    sample_dir = tmp_path / "agg-bad"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = _make_sample(
        sample_id="agg-bad",
        prompt_id="demo",
        sample_dir=sample_dir,
        aggregate=Layer(bind={"r": {"metric": "nope", "k": 0, "over": "sideways"}}),
    )
    errors = validate_samples([sample], [prompt])
    msgs = " ".join(e.message for e in errors)
    assert "nope" in msgs
    assert "k must be an integer" in msgs
    assert "sideways" in msgs


# Rule 4 (positive): setup.files entries that exist in setup/ → no error.
def test_validate_samples_passes_when_setup_files_present(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample-1"
    sample_dir.mkdir()
    setup_dir = sample_dir / "setup"
    (setup_dir / "src").mkdir(parents=True)
    (setup_dir / "src" / "calculator.py").write_text("def add(a, b): return a + b\n")

    prompt = _make_prompt("demo")
    sample = _make_sample(
        sample_id="sample-1",
        prompt_id="demo",
        sample_dir=sample_dir,
        setup_files=["src/calculator.py"],
    )
    assert validate_samples([sample], [prompt]) == []


# Rule 4 (negative): setup.files declares a file not in setup/ → error.
def test_validate_samples_flags_missing_setup_file(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample-2"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = _make_sample(
        sample_id="sample-2",
        prompt_id="demo",
        sample_dir=sample_dir,
        setup_files=["src/missing.py"],
    )
    errors = validate_samples([sample], [prompt])
    assert any(
        isinstance(e, EvalValidationError)
        and "setup.files" in e.message
        and "src/missing.py" in e.message
        for e in errors
    )


# Rule 5 (positive): prompt_id resolves → no error.
def test_validate_samples_passes_when_prompt_id_exists(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample-3"
    sample_dir.mkdir()
    prompt = _make_prompt("demo")
    sample = _make_sample(sample_id="sample-3", prompt_id="demo", sample_dir=sample_dir)
    assert validate_samples([sample], [prompt]) == []


# Rule 5 (negative): unknown prompt_id → error.
def test_validate_samples_flags_unknown_prompt_id(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample-4"
    sample_dir.mkdir()
    sample = _make_sample(sample_id="sample-4", prompt_id="missing", sample_dir=sample_dir)
    errors = validate_samples([sample], [])
    assert any("prompt_id" in e.message and "missing" in e.message for e in errors)


# A prompt's samples are the ones naming it (#281): no list to cross-check.
def test_validate_samples_passes_for_a_sample_naming_a_prompt_that_lists_none(
    tmp_path: Path,
) -> None:
    sample_dir = tmp_path / "sample-6"
    sample_dir.mkdir()
    prompt = _make_prompt("foo")
    sample = _make_sample(sample_id="foo-happy-path", prompt_id="foo", sample_dir=sample_dir)
    assert validate_samples([sample], [prompt]) == []


def test_validate_samples_aggregates_multiple_errors(tmp_path: Path) -> None:
    """The validator collects every violation rather than bailing on the first."""
    sample_dir = tmp_path / "bad-sample"
    sample_dir.mkdir()
    sample = _make_sample(
        sample_id="bad-sample",
        prompt_id="nobody-home",
        sample_dir=sample_dir,
        setup_files=["src/ghost.py"],
    )
    errors = validate_samples([sample], [])
    # Expect two: setup.files miss + prompt_id miss.
    assert len(errors) >= 2
