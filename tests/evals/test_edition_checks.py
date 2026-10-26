"""The offline edition checks CI runs on every pull request (#281 ticket 09).

Each test builds a fixture catalog with a frozen edition and a pinned sample in
``tmp_path``, breaks one thing, and expects exactly the problem naming it.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.edition_checks import edition_problems
from coding_agent_playbook.rendering import session as render_session
from coding_agent_playbook.rendering.prompt_rule_delivery import includes_rules_appendix
from tests.edition_fixtures import (
    PROMPT_PATH,
    SAMPLE_ID,
    TAG,
    freeze_fixture_edition,
    write_digests,
    write_edition_files,
    write_fixture_catalog,
    write_sample,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _frozen(tmp_path: Path) -> Path:
    catalog = write_fixture_catalog(tmp_path, edition=TAG)
    freeze_fixture_edition(catalog)
    return catalog


def _only_problem(catalog: Path) -> str:
    (problem,) = edition_problems(catalog)
    return problem


def test_a_frozen_edition_and_its_pin_have_no_problem(tmp_path: Path) -> None:
    assert edition_problems(_frozen(tmp_path)) == []


def test_a_catalog_without_editions_or_pins_has_no_problem(tmp_path: Path) -> None:
    assert edition_problems(write_fixture_catalog(tmp_path)) == []


def test_a_pin_to_a_missing_edition_is_named(tmp_path: Path) -> None:
    catalog = write_fixture_catalog(tmp_path, edition=TAG)

    problem = _only_problem(catalog)

    assert SAMPLE_ID in problem
    assert f"edition {TAG}" in problem
    assert "does not exist" in problem


def test_an_edition_no_sample_pins_is_named(tmp_path: Path) -> None:
    catalog = write_fixture_catalog(tmp_path)
    write_digests(write_edition_files(catalog))

    problem = _only_problem(catalog)

    assert f"edition {TAG}" in problem
    assert "no eval sample pins it" in problem


def test_a_pin_the_digests_file_does_not_record_is_named(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    write_sample(catalog / "core", edition=TAG, name="second")

    problem = _only_problem(catalog)

    assert "review/second" in problem
    assert "records no pin" in problem


def test_an_edited_edition_file_is_named(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    (catalog / "editions" / TAG / PROMPT_PATH).write_text("edited\n", encoding="utf-8")

    problems = edition_problems(catalog)

    assert any(PROMPT_PATH in p and "differs from its digest" in p for p in problems)


def test_an_edited_pinned_sample_is_named(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    setup = catalog / "core/eval_samples/review/pinned/setup/app.py"
    setup.write_text("x = 2\n", encoding="utf-8")

    problem = _only_problem(catalog)

    assert SAMPLE_ID in problem
    assert "sample digest" in problem


def test_a_renderer_change_that_alters_a_pinned_prompt_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = _frozen(tmp_path)
    # Stand-in for an engine release that changes how a prompt's rules are appended.
    monkeypatch.setattr(
        render_session,
        "includes_rules_appendix",
        lambda ids, registry: includes_rules_appendix(ids, registry) + "\nA new footer.\n",
    )

    problem = _only_problem(catalog)

    assert SAMPLE_ID in problem
    assert "rendered prompt" in problem


def test_an_edition_whose_digests_name_another_tag_is_named(tmp_path: Path) -> None:
    catalog = _frozen(tmp_path)
    shutil.move(catalog / "editions" / TAG, catalog / "editions" / "v9.9.8")

    problems = edition_problems(catalog)

    assert any("names tag" in p for p in problems)
