"""``sample.toml``'s optional ``edition`` key: a pin, accepted only on core samples (#281 ticket 09)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.task_registry import load_task_sample
from tests.edition_fixtures import ENGINE, TAG, write_sample

if TYPE_CHECKING:
    from pathlib import Path


def test_a_core_sample_may_pin_an_edition(tmp_path: Path) -> None:
    sample_dir = write_sample(tmp_path / "catalog/core", edition=TAG)

    assert load_task_sample(sample_dir, source_package=ENGINE).edition == TAG


def test_a_sample_without_the_key_grades_the_current_text(tmp_path: Path) -> None:
    sample_dir = write_sample(tmp_path / "catalog/core", edition=None)

    assert load_task_sample(sample_dir, source_package=ENGINE).edition is None


@pytest.mark.parametrize("layer", ["coding_agent_playbook.plugins.x", "acme.rules", "<repo-local>"])
def test_a_pin_outside_core_is_an_error_naming_the_file(tmp_path: Path, layer: str) -> None:
    sample_dir = write_sample(tmp_path / "playbook", edition=TAG)

    with pytest.raises(ValueError, match="only core samples") as caught:
        load_task_sample(sample_dir, source_package=layer)

    assert str(caught.value).startswith(str(sample_dir / "sample.toml"))


@pytest.mark.parametrize("value", ['""', "3", '"9.9.9"', '"v1/../x"'])
def test_an_edition_that_is_not_a_release_tag_is_refused(tmp_path: Path, value: str) -> None:
    sample_dir = write_sample(tmp_path / "catalog/core", edition=None)
    toml = sample_dir / "sample.toml"
    toml.write_text(f"edition = {value}\n" + toml.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="'edition'"):
        load_task_sample(sample_dir, source_package=ENGINE)
