"""Tests for ``coding_agent_playbook.evals.sample`` dataclasses (C7 schema)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.sample import (
    EvalSample,
    Layer,
    SampleInvocation,
    SampleSetup,
    Verdict,
    compile_eval_sample,
)


def _minimal_dict() -> dict[str, Any]:
    return {
        "id": "demo/happy-path",
        "description": "A demo sample",
    }


def _full_dict() -> dict[str, Any]:
    """A representative sample in the C7 ``[gate]``/``[rubric]``/``[verdict]`` shape."""
    return {
        "id": "generate-tests/happy-path",
        "description": "Generate tests for a simple pure function with no edge cases",
        "setup": {
            "files": ["src/calculator.py"],
            "project_kind": "python-application",
        },
        "invocation": {
            "prompt_args": "for the add function in src/calculator.py",
            "input_variables": {"target": "src/calculator.py::add"},
        },
        "gate": {
            "expr": "created and contains and unchanged",
            "bind": {
                "created": {"check": "file_exists", "path": "tests/test_calculator.py"},
                "contains": {
                    "check": "file_contains",
                    "path": "tests/test_calculator.py",
                    "pattern": "def test_add",
                },
                "unchanged": {"check": "file_unchanged", "path": "src/calculator.py"},
            },
        },
        "rubric": {
            "expr": "quality",
            "bind": {
                "quality": {
                    "fail": 0.5,
                    "rubric": [
                        {"judge": "Tests use pytest.parametrize", "weight": 0.4},
                        {"judge": "Test file mirrors layout", "weight": 0.2},
                        {"judge": "All branches covered", "weight": 0.2},
                        {"judge": "No mocking is used", "weight": 0.2},
                    ],
                },
            },
        },
        "verdict": {"trial": "gate and rubric"},
    }


def _make(data: dict[str, Any], tmp_path: Path, *, prompt_id: str = "demo") -> EvalSample:
    return EvalSample.from_dict(
        data,
        prompt_id=prompt_id,
        source_path=tmp_path / "sample.toml",
        source_package="coding_agent_playbook",
    )


# --- minimal / required-field parsing ----------------------------------------


def test_eval_sample_from_dict_parses_minimal_sample(tmp_path: Path) -> None:
    sample = _make(_minimal_dict(), tmp_path)
    assert sample.id == "demo/happy-path"
    assert sample.prompt_id == "demo"
    assert sample.description == "A demo sample"
    assert sample.source_path == tmp_path / "sample.toml"
    assert sample.source_package == "coding_agent_playbook"
    assert isinstance(sample.setup, SampleSetup)
    assert isinstance(sample.invocation, SampleInvocation)
    # No eval blocks => all None, verdict defaults.
    assert sample.gate is None
    assert sample.rubric is None
    assert sample.aggregate is None
    assert sample.verdict == Verdict(mode="boolean", trial="gate and rubric")


def test_eval_sample_from_dict_parses_full_sample(tmp_path: Path) -> None:
    sample = _make(_full_dict(), tmp_path, prompt_id="generate-tests")
    assert sample.id == "generate-tests/happy-path"
    assert sample.prompt_id == "generate-tests"

    assert sample.setup.files == [Path("src/calculator.py")]
    assert sample.setup.project_kind == "python-application"

    assert sample.invocation.prompt_args.startswith("for the add function")
    assert sample.invocation.input_variables == {"target": "src/calculator.py::add"}

    assert isinstance(sample.gate, Layer)
    assert sample.gate.expr == "created and contains and unchanged"
    assert set(sample.gate.bind) == {"created", "contains", "unchanged"}
    assert sample.gate.bind["created"] == {
        "check": "file_exists",
        "path": "tests/test_calculator.py",
    }

    assert isinstance(sample.rubric, Layer)
    assert sample.rubric.expr == "quality"
    assert sample.rubric.bind["quality"]["fail"] == 0.5
    assert len(sample.rubric.bind["quality"]["rubric"]) == 4

    assert sample.verdict == Verdict(mode="boolean", trial="gate and rubric")


def test_eval_sample_from_dict_rejects_missing_id(tmp_path: Path) -> None:
    data = _minimal_dict()
    del data["id"]
    with pytest.raises(ValueError, match="id"):
        _make(data, tmp_path)


def test_eval_sample_from_dict_rejects_prompt_id_pointing_to_the_task_layout(
    tmp_path: Path,
) -> None:
    data = {**_minimal_dict(), "prompt_id": "demo"}
    with pytest.raises(ValueError, match="unknown top-level key 'prompt_id'") as excinfo:
        _make(data, tmp_path)
    assert "eval_samples/<prompt>/<name>/sample.toml" in str(excinfo.value)


def test_eval_sample_from_dict_rejects_missing_description(tmp_path: Path) -> None:
    data = _minimal_dict()
    del data["description"]
    with pytest.raises(ValueError, match="description"):
        _make(data, tmp_path)


def test_eval_sample_from_dict_rejects_an_unknown_top_level_key_naming_it(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["editon"] = "v0.1.0"
    with pytest.raises(ValueError, match="unknown top-level key 'editon'; allowed keys: id,"):
        _make(data, tmp_path)


def test_eval_sample_from_dict_rejects_version_naming_the_digest(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["version"] = 1
    with pytest.raises(ValueError, match="retired key 'version': the engine now computes"):
        _make(data, tmp_path)


def test_eval_sample_from_dict_rejects_non_string_id(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["id"] = 42
    with pytest.raises(ValueError, match="id"):
        _make(data, tmp_path)


def test_setup_drops_frameworks_and_python_version_from_typed_slots(tmp_path: Path) -> None:
    """C11: ``frameworks`` / ``python_version`` are no longer typed on SampleSetup.

    The dataclass exposes only the typed slots (``files`` / ``project_kind`` /
    ``extra_facts``). The runner installs deps via ``uv sync`` over
    ``setup/pyproject.toml`` instead of reading these dead fields.
    """
    data = _minimal_dict()
    data["setup"] = {
        "files": ["src/x.py"],
        "project_kind": "python-application",
    }
    sample = _make(data, tmp_path)
    assert sample.setup.files == [Path("src/x.py")]
    assert sample.setup.project_kind == "python-application"
    # The typed slots are exactly these two; no ``frameworks``/``python_version`` on
    # the dataclass.
    assert not hasattr(sample.setup, "frameworks")
    assert not hasattr(sample.setup, "python_version")
    assert sample.setup.extra_facts == {}


def test_setup_preserves_unknown_keys_in_extra_facts(tmp_path: Path) -> None:
    """The parser tolerates unknown keys (preserved in ``extra_facts``).

    Overlays mock new detector keys this way (e.g. ``ml_stack`` on the
    shipped ``security-review-*`` samples); the parser keeps that escape hatch
    rather than going strict. Any leftover legacy ``python_version`` /
    ``frameworks`` in an unmigrated fixture lands here too — it is not load-
    bearing (the runner ignores it) but a strict-reject would break the
    overlay extension pattern.
    """
    data = _minimal_dict()
    data["setup"] = {
        "files": ["src/x.py"],
        "project_kind": "ml-research",
        "ml_stack": ["torch"],
        # Stale fields a half-migrated overlay might still carry: harmless,
        # land in extra_facts, do NOT raise.
        "python_version": "3.12",
        "frameworks": ["pytest"],
    }
    sample = _make(data, tmp_path)
    assert sample.setup.extra_facts == {
        "ml_stack": ["torch"],
        "python_version": "3.12",
        "frameworks": ["pytest"],
    }


# --- block shape parsing (structural only; semantics is the compiler's job) ---


def test_gate_parses_bind_and_expr(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {
        "expr": "a",
        "bind": {"a": {"check": "file_exists", "path": "x.py"}},
    }
    sample = _make(data, tmp_path)
    assert isinstance(sample.gate, Layer)
    assert sample.gate.expr == "a"
    assert sample.gate.bind == {"a": {"check": "file_exists", "path": "x.py"}}


def test_gate_expr_optional(tmp_path: Path) -> None:
    """A single-handle gate may omit ``expr`` (the compiler defaults it)."""
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    sample = _make(data, tmp_path)
    assert sample.gate is not None
    assert sample.gate.expr is None


def test_verdict_trial_parses(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    data["verdict"] = {"trial": "gate"}
    sample = _make(data, tmp_path)
    assert sample.verdict == Verdict(mode="boolean", trial="gate")


def test_aggregate_parses_bind_and_expr(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    data["verdict"] = {"trial": "gate"}
    data["aggregate"] = {
        "expr": "pass_rate",
        "bind": {"pass_rate": {"metric": "pass_at_k", "k": 3, "over": "verdict"}},
    }
    sample = _make(data, tmp_path)
    assert isinstance(sample.aggregate, Layer)
    assert sample.aggregate.expr == "pass_rate"
    assert sample.aggregate.bind["pass_rate"] == {"metric": "pass_at_k", "k": 3, "over": "verdict"}


def test_gate_must_be_table(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = []
    with pytest.raises(ValueError, match="gate"):
        _make(data, tmp_path)


def test_gate_bind_must_be_table(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": "nope"}
    with pytest.raises(ValueError, match="bind"):
        _make(data, tmp_path)


def test_gate_bind_handle_must_be_table(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": "nope"}}
    with pytest.raises(ValueError, match=r"bind\.a"):
        _make(data, tmp_path)


def test_gate_expr_must_be_string(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"expr": 42, "bind": {"a": {"check": "file_exists", "path": "x"}}}
    with pytest.raises(ValueError, match="expr"):
        _make(data, tmp_path)


def test_verdict_trial_must_be_string(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["verdict"] = {"trial": 1}
    with pytest.raises(ValueError, match="trial"):
        _make(data, tmp_path)


# --- compile_eval_sample / EvalSample.compiled -----------------------------------


def test_compiled_builds_layer_checks(tmp_path: Path) -> None:
    sample = _make(_full_dict(), tmp_path, prompt_id="generate-tests")
    compiled = compile_eval_sample(sample)
    assert [c.id for c in compiled.per_trial.checks] == ["gate", "rubric"]
    assert compiled.layers == frozenset({"gate", "rubric"})


def test_compiled_method_matches_free_function(tmp_path: Path) -> None:
    sample = _make(_full_dict(), tmp_path, prompt_id="generate-tests")
    via_method = sample.compiled()
    assert via_method.layers == frozenset({"gate", "rubric"})
    assert [c.id for c in via_method.per_trial.checks] == ["gate", "rubric"]


def test_compile_raises_on_no_layer(tmp_path: Path) -> None:
    """A sample with no [gate] and no [rubric] cannot compile (at-least-one rule)."""
    sample = _make(_minimal_dict(), tmp_path)
    with pytest.raises(ValueError, match="at least one"):
        compile_eval_sample(sample)


def test_compile_raises_on_unknown_check(tmp_path: Path) -> None:
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "not_a_real_check", "path": "x"}}}
    data["verdict"] = {"trial": "gate"}
    sample = _make(data, tmp_path)
    with pytest.raises(KeyError):
        compile_eval_sample(sample)


# --- C10: weighted-composite verdict parsing + compile-time guards -----------


def _weighted_layers_data() -> dict[str, Any]:
    """A sample with both layers present so a weighted-verdict tests have a valid base."""
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    data["rubric"] = {
        "bind": {
            "q": {
                "fail": 0.5,
                "rubric": [{"judge": "c", "weight": 1.0}],
            }
        }
    }
    return data


def test_verdict_weighted_form_parses(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {"gate": 0.4, "rubric": 0.6}, "fail": 0.7}
    sample = _make(data, tmp_path)
    assert sample.verdict.mode == "weighted"
    assert sample.verdict.trial is None
    assert sample.verdict.weights == {"gate": 0.4, "rubric": 0.6}
    assert sample.verdict.fail == 0.7
    assert sample.verdict.warn is None


def test_verdict_weighted_form_with_warn_parses(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {
        "weights": {"gate": 0.4, "rubric": 0.6},
        "fail": 0.5,
        "warn": 0.8,
    }
    sample = _make(data, tmp_path)
    assert sample.verdict.warn == 0.8


def test_verdict_weighted_form_rejects_trial_alongside_weights(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {
        "trial": "gate and rubric",
        "weights": {"gate": 0.4, "rubric": 0.6},
        "fail": 0.5,
    }
    with pytest.raises(ValueError, match="cannot set both"):
        _make(data, tmp_path)


def test_verdict_weighted_form_rejects_weights_not_summing_to_one(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {"gate": 0.3, "rubric": 0.5}, "fail": 0.5}
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        _make(data, tmp_path)


def test_verdict_weighted_form_requires_fail(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {"gate": 0.4, "rubric": 0.6}}
    with pytest.raises(ValueError, match="requires 'fail'"):
        _make(data, tmp_path)


def test_verdict_weighted_form_rejects_empty_weights(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {}, "fail": 0.5}
    with pytest.raises(ValueError, match="non-empty"):
        _make(data, tmp_path)


def test_verdict_weighted_form_rejects_fail_out_of_range(tmp_path: Path) -> None:
    data = _weighted_layers_data()
    data["verdict"] = {"weights": {"gate": 0.4, "rubric": 0.6}, "fail": 1.5}
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        _make(data, tmp_path)


def test_compile_raises_on_unknown_layer_in_weights(tmp_path: Path) -> None:
    """Weights referencing a non-present layer is caught at compile time."""
    data = _minimal_dict()
    data["gate"] = {"bind": {"a": {"check": "file_exists", "path": "x.py"}}}
    # No [rubric], yet weights mention it.
    data["verdict"] = {"weights": {"gate": 0.4, "rubric": 0.6}, "fail": 0.5}
    sample = _make(data, tmp_path)
    with pytest.raises(ValueError, match="unknown layer"):
        compile_eval_sample(sample)


@pytest.mark.parametrize("ml_stack", ["torch", [["torch"]], {"torch": 2}, 3])
def test_setup_rejects_malformed_ml_stack_mock(tmp_path: Path, ml_stack: Any) -> None:
    """A mocked ``ml_stack`` gates rules at render time; a bad shape must fail at
    parse (so ``playbook validate`` reports it), not later at ``--run``."""
    data = _minimal_dict()
    data["setup"] = {"ml_stack": ml_stack}

    with pytest.raises(ValueError, match=r"\[setup\]\.ml_stack must be a list of names"):
        _make(data, tmp_path)


@pytest.mark.parametrize("ml_stack", [["torch", "jax"], {"torch": ">=2"}, []])
def test_setup_accepts_list_or_table_ml_stack_mock(tmp_path: Path, ml_stack: Any) -> None:
    data = _minimal_dict()
    data["setup"] = {"ml_stack": ml_stack}

    assert _make(data, tmp_path).setup.extra_facts["ml_stack"] == ml_stack
