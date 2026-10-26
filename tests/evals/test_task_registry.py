"""Tests for the task registry (``evals.task_registry``, #302): tasks, lookups and errors."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.catalog.source import ArtifactSource
from coding_agent_playbook.evals.sample import EvalSample
from coding_agent_playbook.evals.task_registry import (
    TaskRegistry,
    TaskRegistryError,
    collect_layer_samples,
    load_layer_samples,
    sample_layer_root,
)

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

_PROMPTS = ("review", "refactor", "explain")


def _sample(sample_id: str, *, layer: str = "core", package: str = "engine") -> EvalSample:
    """A sample of the task its id names, at ``<layer>/eval_samples/<prompt>/<name>/sample.toml``."""
    task = sample_id.split("/")[0]
    return EvalSample(
        id=sample_id,
        prompt_id=task,
        description="",
        source_path=Path(layer) / "eval_samples" / sample_id / "sample.toml",
        source_package=package,
    )


def _write_sample(root: Path, sample_id: str, *, body: str = 'description = "d"\n') -> Path:
    sample_dir = root / sample_id
    sample_dir.mkdir(parents=True)
    (sample_dir / "sample.toml").write_text(f'id = "{sample_id}"\n{body}', encoding="utf-8")
    return sample_dir


# --------------------------------------------------------------------------- #
# Registering
# --------------------------------------------------------------------------- #


def test_registers_each_task_under_its_prompt_id_with_its_samples() -> None:
    registry = TaskRegistry.build(
        [_sample("review/b"), _sample("refactor/x"), _sample("review/a")], _PROMPTS
    )

    assert [task.prompt_id for task in registry.tasks()] == ["refactor", "review"]
    assert [s.id for s in registry.task("review").samples] == ["review/a", "review/b"]


def test_a_later_layer_adds_samples_to_an_existing_task() -> None:
    core = _sample("review/spot-the-bug")
    local = _sample("review/our-style", layer="playbook", package="<repo-local>")

    registry = TaskRegistry.build([core, local], _PROMPTS)

    assert [s.id for s in registry.samples_of("review")] == [
        "review/our-style",
        "review/spot-the-bug",
    ]


def test_a_sample_id_registered_twice_is_an_error_naming_both_sources() -> None:
    first = _sample("review/spot-the-bug")
    second = _sample("review/spot-the-bug", layer="playbook", package="<repo-local>")

    with pytest.raises(TaskRegistryError) as excinfo:
        TaskRegistry.build([first, second], _PROMPTS)

    message = str(excinfo.value)
    assert "'review/spot-the-bug'" in message
    assert str(first.source_path) in message
    assert str(second.source_path) in message


def test_a_task_whose_prompt_does_not_exist_is_rejected_naming_its_directory() -> None:
    orphan = _sample("deleted-prompt/case")

    with pytest.raises(TaskRegistryError) as excinfo:
        TaskRegistry.build([orphan], _PROMPTS)

    assert "'deleted-prompt'" in str(excinfo.value)
    assert str(Path("core/eval_samples/deleted-prompt")) in str(excinfo.value)
    assert excinfo.value.path == Path("core/eval_samples/deleted-prompt")


def test_collect_keeps_every_good_sample_and_returns_every_error() -> None:
    samples = [_sample("review/a"), _sample("review/a"), _sample("gone/x"), _sample("explain/e")]

    registry, errors = TaskRegistry.collect(samples, _PROMPTS)

    assert [task.prompt_id for task in registry.tasks()] == ["explain", "review"]
    assert len(errors) == 2


class FakeThirdPartySource(ArtifactSource):
    """A non-filesystem artifact source: it serves samples it built itself."""

    name = "fake-remote"

    def __init__(self, samples: list[EvalSample], *, error: ValueError | None = None) -> None:
        self._samples = samples
        self._error = error

    def list_rules(self) -> list[Rule]:
        return []

    def list_prompts(self) -> list[Prompt]:
        return []

    def list_skills(self) -> list[Skill]:
        return []

    def list_eval_samples(self) -> list[EvalSample]:
        if self._error is not None:
            raise self._error
        return self._samples


def _prompt(prompt_id: str) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(id=prompt_id, name=prompt_id, description="p", slash="p"),
        body="",
        template_body="",
        is_templated=False,
        source_path=None,
        source_package="fake-remote",
    )


def test_from_catalog_registers_a_third_party_sources_samples() -> None:
    source = FakeThirdPartySource([_sample("review/remote", package="fake-remote")])

    registry = TaskRegistry.from_catalog(source, [_prompt("review")])

    assert [s.id for s in registry.samples_of("review")] == ["review/remote"]


def test_a_third_party_sources_load_error_is_collected_not_raised() -> None:
    source = FakeThirdPartySource([], error=ValueError("remote sample is broken"))

    samples, errors = source.collect_eval_samples()

    assert samples == []
    assert [str(e) for e in errors] == ["remote sample is broken"]


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #


def test_task_of_a_sample_id_is_the_task_it_was_registered_under() -> None:
    registry = TaskRegistry.build([_sample("review/a"), _sample("explain/e")], _PROMPTS)

    assert registry.task_of("explain/e").prompt_id == "explain"
    assert registry.sample("review/a").id == "review/a"


def test_an_unknown_task_lists_the_known_ones() -> None:
    registry = TaskRegistry.build([_sample("review/a"), _sample("explain/e")], _PROMPTS)

    with pytest.raises(TaskRegistryError, match=r"no task 'revue'; known tasks: explain, review"):
        registry.task("revue")


def test_an_unknown_sample_id_lists_the_known_tasks() -> None:
    registry = TaskRegistry.build([_sample("review/a")], _PROMPTS)

    with pytest.raises(TaskRegistryError, match=r"no eval sample 'review/z'.*known tasks: review"):
        registry.task_of("review/z")


def test_select_a_task_name_selects_every_sample_of_the_task() -> None:
    registry = TaskRegistry.build(
        [_sample("review/a"), _sample("review/b"), _sample("explain/e")], _PROMPTS
    )

    assert [s.id for s in registry.select("review")] == ["review/a", "review/b"]


def test_select_a_sample_id_selects_only_that_sample() -> None:
    registry = TaskRegistry.build([_sample("review/a"), _sample("review/b")], _PROMPTS)

    assert [s.id for s in registry.select("review/b")] == ["review/b"]


def test_select_an_unknown_name_is_an_error() -> None:
    registry = TaskRegistry.build([_sample("review/a")], _PROMPTS)

    with pytest.raises(TaskRegistryError, match="known tasks: review"):
        registry.select("nope")


# --------------------------------------------------------------------------- #
# Discovery in one layer's eval_samples/
# --------------------------------------------------------------------------- #


def test_load_layer_samples_reads_task_directories(tmp_path: Path) -> None:
    root = tmp_path / "eval_samples"
    _write_sample(root, "review/spot-the-bug")
    _write_sample(root, "explain/pure-function")
    (root / "ATTRIBUTIONS.md").write_text("credits\n", encoding="utf-8")
    (root / ".cache" / "x").mkdir(parents=True)
    (root / "review" / "draft-without-toml").mkdir()

    samples = load_layer_samples(root, "engine")

    assert [(s.id, s.prompt_id, s.source_package) for s in samples] == [
        ("explain/pure-function", "explain", "engine"),
        ("review/spot-the-bug", "review", "engine"),
    ]


def test_a_missing_eval_samples_directory_has_no_samples(tmp_path: Path) -> None:
    assert collect_layer_samples(tmp_path / "eval_samples", "engine") == ([], [])


def test_a_sample_in_the_old_flat_layout_is_an_error_naming_the_directory(tmp_path: Path) -> None:
    root = tmp_path / "eval_samples"
    flat = _write_sample(root, "review-spot-the-bug")

    samples, errors = collect_layer_samples(root, "engine")

    assert samples == []
    assert [e.path for e in errors] == [flat]
    assert "eval_samples/<prompt>/<name>/" in str(errors[0])


def test_a_sample_whose_id_does_not_match_its_directory_is_an_error(tmp_path: Path) -> None:
    root = tmp_path / "eval_samples"
    sample_dir = root / "review" / "spot-the-bug"
    sample_dir.mkdir(parents=True)
    (sample_dir / "sample.toml").write_text(
        'id = "review-spot-the-bug"\ndescription = "d"\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="id 'review-spot-the-bug' does not match"):
        load_layer_samples(root, "engine")


def test_a_sample_toml_with_prompt_id_is_rejected_pointing_to_the_layout(tmp_path: Path) -> None:
    root = tmp_path / "eval_samples"
    _write_sample(root, "review/old", body='prompt_id = "review"\ndescription = "d"\n')

    _, errors = collect_layer_samples(root, "engine")

    assert len(errors) == 1
    assert "unknown top-level key 'prompt_id'" in str(errors[0])
    assert "eval_samples/<prompt>/<name>/sample.toml" in str(errors[0])


def test_sample_layer_root_is_the_layer_holding_the_task_directory() -> None:
    toml = Path("catalog/core/eval_samples/review/spot-the-bug/sample.toml")

    assert sample_layer_root(toml) == Path("catalog/core")
    assert sample_layer_root(Path("elsewhere/sample.toml")) is None
