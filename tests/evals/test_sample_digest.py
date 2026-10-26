"""The sample and prompt digests release metrics record (``evals.sample_digest``, ticket 07)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evals.sample import EvalSample
from coding_agent_playbook.evals.sample_digest import prompt_digest, sample_digest

if TYPE_CHECKING:
    from pathlib import Path

_PROMPT = """\
---
id: tidy
name: Tidy
slash: tidy
description: Tidy the module.
---
Tidy the module.
"""


def _sample(layer: Path) -> EvalSample:
    sample_dir = layer / "eval_samples" / "tidy-one"
    (sample_dir / "setup").mkdir(parents=True)
    (sample_dir / "sample.toml").write_text('id = "tidy-one"\n', encoding="utf-8")
    (sample_dir / "setup" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    return EvalSample(
        id="tidy-one",
        prompt_id="tidy",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package="<repo-local>",
    )


def test_sample_digest_moves_with_sample_toml_and_setup_but_not_with_caches(
    tmp_path: Path,
) -> None:
    sample = _sample(tmp_path)
    before = sample_digest(sample)
    cache = sample.source_path.parent / "setup" / "__pycache__"
    cache.mkdir()
    (cache / "mod.cpython-312.pyc").write_bytes(b"\0")
    assert sample_digest(sample) == before

    (sample.source_path.parent / "setup" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    after_setup = sample_digest(sample)
    assert after_setup != before

    sample.source_path.write_text('id = "tidy-one"\n# edited\n', encoding="utf-8")
    assert sample_digest(sample) != after_setup


def test_prompt_digest_is_the_graded_prompt_artifact_digest(tmp_path: Path) -> None:
    sample = _sample(tmp_path)
    assert prompt_digest(sample) is None
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "tidy.md").write_text(_PROMPT, encoding="utf-8")
    first = prompt_digest(sample)
    assert first is not None and len(first) == 64
    (prompts / "tidy.md").write_text(_PROMPT + "Keep names.\n", encoding="utf-8")
    assert prompt_digest(sample) != first
