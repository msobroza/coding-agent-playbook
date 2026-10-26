"""``release.graded_set`` and ``release.snapshot`` over the shipped catalog (ADR 0012)."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.catalog.digest import artifact_digest
from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.catalog.roots import catalog_root
from coding_agent_playbook.release.graded_set import (
    GradedSetError,
    core_graded_prompt_ids,
    graded_set,
)
from coding_agent_playbook.release.manifest import parse_manifest, render_manifest
from coding_agent_playbook.release.snapshot import build_manifest, shipped_source
from tests._catalog import REPO_ROOT

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.catalog.source import FileSystemArtifactSource
    from coding_agent_playbook.release.manifest import ReleaseManifest

pytestmark = pytest.mark.catalog


@functools.cache
def _source() -> FileSystemArtifactSource:
    return shipped_source(REPO_ROOT, catalog_root())


@functools.cache
def _manifest() -> ReleaseManifest:
    return build_manifest(_source(), catalog_root(), version="9.9.9", base="f00d")


def _core_prompts_and_rules() -> tuple[list[Prompt], list[Rule]]:
    source = _source()
    prompts = [p for p in source.list_prompts() if p.source_package == ENGINE_PACKAGE]
    rules = [r for r in source.list_rules() if r.source_package == ENGINE_PACKAGE]
    return prompts, rules


def test_graded_prompts_are_the_prompts_core_samples_grade() -> None:
    ids = core_graded_prompt_ids(_source())
    samples = _source().list_eval_samples()

    assert ids == sorted({s.prompt_id for s in samples if s.source_package == ENGINE_PACKAGE})
    assert "review" in ids


def test_graded_set_holds_each_graded_prompt_and_every_rule_it_includes() -> None:
    prompts, rules = _core_prompts_and_rules()

    graded = graded_set(["review"], prompts, rules)

    (review,) = graded.prompts
    assert review.frontmatter.id == "review"
    assert [r.frontmatter.id for r in graded.rules] == sorted(review.frontmatter.includes_rules)


def test_graded_set_names_a_prompt_core_does_not_ship() -> None:
    prompts, rules = _core_prompts_and_rules()

    with pytest.raises(GradedSetError, match="graded prompt 'no-such-task' is not a core prompt"):
        graded_set(["no-such-task"], prompts, rules)


def test_graded_set_names_an_included_rule_core_does_not_ship() -> None:
    prompts, _ = _core_prompts_and_rules()
    includer = next(p for p in prompts if p.frontmatter.includes_rules)

    with pytest.raises(GradedSetError, match="graded rule"):
        graded_set([includer.frontmatter.id], prompts, [])


def test_manifest_records_the_graded_set_with_repo_paths_and_digests() -> None:
    manifest = _manifest()
    prompts, rules = _core_prompts_and_rules()
    graded = graded_set(core_graded_prompt_ids(_source()), prompts, rules)
    by_path = {(REPO_ROOT / e.path): e for e in manifest.graded}

    graded_files: list[Prompt | Rule] = [*graded.prompts, *graded.rules]
    expected = {a.source_path: artifact_digest(a) for a in graded_files}
    assert {path: e.digest for path, e in by_path.items()} == expected
    assert all(e.path.startswith("catalog/core/") for e in manifest.graded)


def test_manifest_lists_every_shipped_layer_and_kind_and_round_trips() -> None:
    manifest = _manifest()
    layers = {e.layer for e in manifest.artifacts}
    kinds = {e.kind for e in manifest.artifacts}

    assert ENGINE_PACKAGE in layers
    assert any(layer.startswith(f"{ENGINE_PACKAGE}.plugins.") for layer in layers)
    assert kinds == {"rule", "prompt", "skill", "hook"}
    assert set(manifest.graded) <= set(manifest.artifacts)
    assert all((REPO_ROOT / e.path).exists() for e in manifest.artifacts)
    assert parse_manifest(render_manifest(manifest)) == manifest
