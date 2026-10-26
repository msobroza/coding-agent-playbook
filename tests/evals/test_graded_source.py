"""What an eval run grades: a pinned sample's edition, or the current text (#281 ticket 09)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import coding_agent_playbook
from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.catalog.digest import artifact_digest
from coding_agent_playbook.evals.graded_source import graded_record, graded_source
from coding_agent_playbook.evals.sample_digest import sample_digest
from coding_agent_playbook.evals.task_registry import load_task_sample
from coding_agent_playbook.release.edition import EditionError
from tests.edition_fixtures import (
    ENGINE,
    PROMPT_PATH,
    TAG,
    freeze_fixture_edition,
    write_fixture_catalog,
)

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.sample import EvalSample


def _sample(catalog: Path) -> EvalSample:
    return load_task_sample(catalog / "core/eval_samples/review/pinned", source_package=ENGINE)


def test_a_pinned_sample_grades_its_edition(tmp_path: Path) -> None:
    catalog = write_fixture_catalog(tmp_path, edition=TAG)
    freeze_fixture_edition(catalog)

    source = graded_source(_sample(catalog))

    assert source.edition is not None
    assert source.edition.root == catalog / "editions" / TAG
    assert source.note == f"graded edition {TAG} (frozen; overrides ignored)"


def test_head_grades_the_current_text_even_for_a_pinned_sample(tmp_path: Path) -> None:
    catalog = write_fixture_catalog(tmp_path, edition=TAG)

    source = graded_source(_sample(catalog), head=True)

    assert source.edition is None
    assert source.label == "head"
    assert source.note == "graded head"


def test_a_pin_to_a_missing_edition_is_an_error(tmp_path: Path) -> None:
    catalog = write_fixture_catalog(tmp_path, edition=TAG)

    with pytest.raises(EditionError, match="no edition"):
        graded_source(_sample(catalog))


def test_the_record_names_the_source_digests_and_engine_version(tmp_path: Path) -> None:
    catalog = write_fixture_catalog(tmp_path, edition=TAG)
    freeze_fixture_edition(catalog)
    sample = _sample(catalog)
    source = graded_source(sample)

    record = graded_record(sample, source)

    assert record.source == TAG
    assert record.prompt_digest == artifact_digest(source.edition.prompt("review"))  # type: ignore[union-attr]
    assert record.sample_digest == sample_digest(sample)
    assert record.engine_version == coding_agent_playbook.__version__
    assert record.as_dict()["source"] == TAG


def test_the_head_record_digests_the_current_prompt(tmp_path: Path) -> None:
    catalog = write_fixture_catalog(tmp_path, edition=None)
    sample = _sample(catalog)

    record = graded_record(sample, graded_source(sample))

    assert record.source == "head"
    current = Prompt.from_markdown(catalog / PROMPT_PATH, ENGINE)
    assert record.prompt_digest == artifact_digest(current)
