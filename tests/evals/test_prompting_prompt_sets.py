"""An eval sample grades v1 unless a run asks for another prompt set (D76; prU L0-24).

The opt-in eval comparison (D37) runs the same samples with each prompt set, so
``render_prompt`` takes the set to render; like sync, a prompt with no twin in
that set keeps its v1 text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.sample import EvalSample, SampleInvocation, SampleSetup

if TYPE_CHECKING:
    from pathlib import Path


def _write_prompt(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nid: synthetic\nname: Synthetic\ndescription: d\nslash: synthetic\n---\n" + body,
        encoding="utf-8",
    )


def _sample(tmp_path: Path, *, with_v2: bool = True) -> EvalSample:
    """``<tmp>/layer/{prompts,eval_samples}``: a v1 prompt, maybe its v2 twin, one sample."""
    layer = tmp_path / "layer"
    _write_prompt(layer / "prompts" / "synthetic.md", "Version one.\n")
    if with_v2:
        _write_prompt(layer / "prompts" / "v2" / "synthetic.md", "Version two.\n")
    sample_dir = layer / "eval_samples" / "synthetic-sample"
    (sample_dir / "setup").mkdir(parents=True)
    return EvalSample(
        id="synthetic-sample",
        prompt_id="synthetic",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package="coding_agent_playbook",
        setup=SampleSetup(),
        invocation=SampleInvocation(prompt_args="go"),
    )


def test_a_sample_renders_its_v1_prompt_by_default(tmp_path: Path) -> None:
    assert render_prompt(_sample(tmp_path), strict=True) == "Version one.\n\n\ngo"


def test_a_run_can_render_the_v2_twin(tmp_path: Path) -> None:
    assert render_prompt(_sample(tmp_path), strict=True, prompt_set="v2") == "Version two.\n\n\ngo"


def test_a_prompt_without_a_twin_keeps_its_v1_text_in_v2(tmp_path: Path) -> None:
    sample = _sample(tmp_path, with_v2=False)
    assert render_prompt(sample, strict=True, prompt_set="v2") == "Version one.\n\n\ngo"
