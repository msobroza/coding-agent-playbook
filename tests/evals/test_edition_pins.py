"""Pinning and unpinning the graded core samples to an edition (#281 ticket 13).

Fixture catalogs come from ``tests.edition_fixtures``; the edition's files are
written as ``freeze`` writes them, then the samples are pinned for real.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.edition_checks import edition_problems
from coding_agent_playbook.evals.edition_pins import (
    EditionPinError,
    pin_graded_samples,
    unpin_samples,
    with_edition_line,
    without_edition_line,
)
from coding_agent_playbook.release.edition_digests import DIGESTS_FILENAME, read_edition_digests
from coding_agent_playbook.release.edition_freeze import write_edition_digests
from tests.edition_fixtures import (
    SAMPLE_ID,
    TAG,
    write_digests,
    write_edition_files,
    write_fixture_catalog,
    write_sample,
)

if TYPE_CHECKING:
    from pathlib import Path

SAMPLE_TOML = "core/eval_samples/review/pinned/sample.toml"


def _unpinned_edition(tmp_path: Path) -> Path:
    catalog = write_fixture_catalog(tmp_path)
    write_digests(write_edition_files(catalog))
    return catalog


def _pin(catalog: Path, prompt_ids: list[str]) -> None:
    root = catalog / "editions" / TAG
    pins = pin_graded_samples(catalog, TAG, prompt_ids)
    write_edition_digests(root, read_edition_digests(root / DIGESTS_FILENAME), pins)


def test_pinning_sets_the_edition_and_records_digests_the_offline_checks_accept(
    tmp_path: Path,
) -> None:
    catalog = _unpinned_edition(tmp_path)

    _pin(catalog, ["review"])

    data = tomllib.loads((catalog / SAMPLE_TOML).read_text(encoding="utf-8"))
    assert data["edition"] == TAG
    pins = read_edition_digests(catalog / "editions" / TAG / DIGESTS_FILENAME).pins
    assert [pin.sample for pin in pins] == [SAMPLE_ID]
    assert edition_problems(catalog) == []


def test_pinning_again_is_idempotent(tmp_path: Path) -> None:
    catalog = _unpinned_edition(tmp_path)
    _pin(catalog, ["review"])
    before = (catalog / SAMPLE_TOML).read_bytes()

    _pin(catalog, ["review"])

    assert (catalog / SAMPLE_TOML).read_bytes() == before
    assert edition_problems(catalog) == []


def test_only_samples_of_graded_prompts_are_pinned(tmp_path: Path) -> None:
    catalog = _unpinned_edition(tmp_path)
    task = catalog / "core/eval_samples/explain"
    task.mkdir()
    other = write_sample(catalog / "core", edition=None, name="plain").rename(task / "plain")
    toml = other / "sample.toml"
    toml.write_text(toml.read_text("utf-8").replace("review/plain", "explain/plain"), "utf-8")

    pins = pin_graded_samples(catalog, TAG, ["review"])

    assert [pin.sample for pin in pins] == [SAMPLE_ID]
    assert "edition" not in tomllib.loads(toml.read_text("utf-8"))


def test_a_sample_pinned_to_another_edition_refuses(tmp_path: Path) -> None:
    catalog = _unpinned_edition(tmp_path)
    write_sample(catalog / "core", edition="v9.9.8", name="older")

    with pytest.raises(EditionPinError, match=r"review/older \(v9\.9\.8\).*unfreeze"):
        pin_graded_samples(catalog, TAG, ["review"])


def test_no_sample_to_pin_refuses(tmp_path: Path) -> None:
    catalog = _unpinned_edition(tmp_path)

    with pytest.raises(EditionPinError, match="no core eval sample grades"):
        pin_graded_samples(catalog, TAG, ["characterize"])


def test_unpinning_removes_only_that_editions_line(tmp_path: Path) -> None:
    catalog = _unpinned_edition(tmp_path)
    before = (catalog / SAMPLE_TOML).read_bytes()
    _pin(catalog, ["review"])

    assert unpin_samples(catalog, TAG) == [SAMPLE_ID]

    assert (catalog / SAMPLE_TOML).read_bytes() == before
    assert unpin_samples(catalog, TAG) == []


def test_the_edition_line_goes_after_the_top_level_keys() -> None:
    text = 'id = "review/x"\ndescription = "d"\n\n[gate]\nexpr = "a"\n'

    pinned = with_edition_line(text, TAG)

    assert (
        pinned == f'id = "review/x"\ndescription = "d"\nedition = "{TAG}"\n\n[gate]\nexpr = "a"\n'
    )
    assert without_edition_line(pinned) == text


def test_an_existing_edition_line_is_replaced() -> None:
    text = 'id = "review/x"\nedition = "v9.9.8"\n'

    assert with_edition_line(text, TAG) == f'id = "review/x"\nedition = "{TAG}"\n'


def test_a_file_without_tables_gets_the_line_at_the_end() -> None:
    assert with_edition_line('id = "review/x"\n', TAG) == f'id = "review/x"\nedition = "{TAG}"\n'


@pytest.mark.parametrize(
    "text",
    [
        'id = "review/x"',
        'id = "review/x"\r\ndescription = "d"',
        'id = "review/x"\n\n[gate]\nexpr = "a"',
        'id = "review/x"\n# a closing comment',
        'id = "review/x"\nedition = "v9.9.8"',
    ],
    ids=["no-newline", "crlf-no-newline", "table-no-newline", "comment-no-newline", "re-pin"],
)
def test_unpinning_gives_back_the_exact_bytes_of_a_file_without_a_final_newline(
    text: str,
) -> None:
    """Regression: pinning added a final newline that unpinning left behind (#319 review)."""
    pinned = with_edition_line(text, TAG)

    assert not pinned.endswith("\n")
    assert without_edition_line(pinned) == without_edition_line(text)
    if "edition" not in text:
        assert without_edition_line(pinned) == text


def test_unpinning_a_sample_without_a_final_newline_restores_its_bytes(tmp_path: Path) -> None:
    catalog = _unpinned_edition(tmp_path)
    sample = catalog / SAMPLE_TOML
    sample.write_bytes(sample.read_bytes().rstrip(b"\n"))
    before = sample.read_bytes()
    _pin(catalog, ["review"])
    assert sample.read_bytes() != before

    unpin_samples(catalog, TAG)

    assert sample.read_bytes() == before


def test_an_edit_that_would_change_other_keys_refuses() -> None:
    text = 'id = "review/x"\ndescription = """\n[not a table]\n"""\n'

    with pytest.raises(EditionPinError, match="edit by hand"):
        with_edition_line(text, TAG)
