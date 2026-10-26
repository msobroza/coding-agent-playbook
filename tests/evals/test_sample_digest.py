"""The sample, prompt and inputs digests release metrics record (``evals.sample_digest``).

Ticket 07 of #281 added the sample and prompt digests, ticket 03 of #329 the inputs digest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.catalog import roots as catalog_roots
from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.sample import EvalSample
from coding_agent_playbook.evals.sample_digest import inputs_digest, prompt_digest, sample_digest
from coding_agent_playbook.evals.task_registry import load_task_sample

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
    sample_dir = layer / "eval_samples" / "tidy" / "tidy-one"
    (sample_dir / "setup").mkdir(parents=True)
    (sample_dir / "sample.toml").write_text('id = "tidy/tidy-one"\n', encoding="utf-8")
    (sample_dir / "setup" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    return EvalSample(
        id="tidy/tidy-one",
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


# --------------------------------------------------------------------------- #
# Inputs digest (#329 ticket 03): what the agent receives, plus the sample
# --------------------------------------------------------------------------- #

_ENGINE: Final = "coding_agent_playbook"
_RULE_PATH: Final = "core/rules/typing.md"
_RULE: Final = (
    "---\nid: typing\nname: Typing\ndescription: Type everything.\nscope: always\n---\n{body}"
)
_REVIEW_PROMPT: Final = (
    "---\nid: review\nname: Review\ndescription: Review code.\nslash: review\n{extra}"
    "includes_rules:\n  - typing\n---\nReview the code.\n"
)
_SAMPLE_TOML: Final = (
    'id = "{id}"\ndescription = "d"\n\n'
    '[gate.bind.ok]\ncheck = "file_exists"\npath = "app.py"\n\n[verdict]\ntrial = "gate"\n'
)
#: Two samples of the ``review`` prompt (it includes ``typing``) and one of ``tidy`` (none).
_SAMPLE_DIRS: Final = {
    "review/a": "core/eval_samples/review/a",
    "review/b": "core/eval_samples/review/b",
    "tidy/c": "core/eval_samples/tidy/c",
}


@pytest.fixture
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An engine catalog holding the ``review`` and ``tidy`` prompts, ``typing`` and 3 samples."""
    catalog = tmp_path / "engine" / "catalog"
    monkeypatch.setattr(
        catalog_roots, "_PACKAGE_DIR", tmp_path / "engine" / "src" / "coding_agent_playbook"
    )
    _write(catalog / "core" / "prompts" / "review.md", _REVIEW_PROMPT.format(extra=""))
    _write(catalog / "core" / "prompts" / "tidy.md", _PROMPT)
    _write(catalog / _RULE_PATH, _RULE.format(body="Type everything.\n"))
    for sample_id, rel in _SAMPLE_DIRS.items():
        _write(catalog / rel / "sample.toml", _SAMPLE_TOML.format(id=sample_id))
        _write(catalog / rel / "setup" / "app.py", "x = 1\n")
    return catalog


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _inputs_digests(catalog: Path) -> dict[str, str]:
    """Each sample's inputs digest, from the strict render a recording does."""
    digests = {}
    for sample_id, rel in _SAMPLE_DIRS.items():
        sample = load_task_sample(catalog / rel, source_package=_ENGINE)
        digests[sample_id] = inputs_digest(sample, render_prompt(sample, strict=True))
    return digests


def _changed(before: dict[str, str], after: dict[str, str]) -> set[str]:
    return {sample_id for sample_id, digest in before.items() if digest != after[sample_id]}


def test_inputs_digest_is_stable_and_distinct_per_sample(engine: Path) -> None:
    first = _inputs_digests(engine)
    assert first == _inputs_digests(engine)
    assert all(len(digest) == 64 for digest in first.values())
    assert len(set(first.values())) == len(first)


def test_editing_an_included_rule_changes_only_the_samples_including_it(engine: Path) -> None:
    before = _inputs_digests(engine)
    _write(engine / _RULE_PATH, _RULE.format(body="Type everything, strictly.\n"))
    assert _changed(before, _inputs_digests(engine)) == {"review/a", "review/b"}


@pytest.mark.parametrize("edited", ["sample.toml", "setup/app.py"])
def test_editing_a_sample_changes_only_its_own_inputs_digest(engine: Path, edited: str) -> None:
    before = _inputs_digests(engine)
    path = engine / _SAMPLE_DIRS["review/a"] / edited
    path.write_text(path.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    assert _changed(before, _inputs_digests(engine)) == {"review/a"}


def test_frontmatter_the_agent_never_receives_leaves_the_digest_unchanged(engine: Path) -> None:
    before = _inputs_digests(engine)
    contract = "output_contract:\n  - findings\n"
    _write(engine / "core" / "prompts" / "review.md", _REVIEW_PROMPT.format(extra=contract))
    assert _inputs_digests(engine) == before


def test_inputs_digest_moves_with_the_rendered_text(tmp_path: Path) -> None:
    sample = _sample(tmp_path)
    assert inputs_digest(sample, "Tidy.") != inputs_digest(sample, "Tidy!")
