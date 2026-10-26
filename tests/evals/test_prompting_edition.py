"""A pinned sample renders its edition's frozen prompt and rules, closed-world (#281 ticket 09)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.prompting import PromptResolutionError, render_prompt
from coding_agent_playbook.evals.task_registry import load_task_sample
from coding_agent_playbook.release.edition import load_edition
from tests.edition_fixtures import (
    CURRENT_PROMPT_BODY,
    ENGINE,
    FROZEN_PROMPT_BODY,
    FROZEN_RULE_BODY,
    OVERRIDE_RULE_BODY,
    TAG,
    write_digests,
    write_edition_files,
    write_fixture_catalog,
    write_local_rule_override,
)

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.sample import EvalSample


def _pinned(tmp_path: Path) -> tuple[Path, EvalSample]:
    catalog = write_fixture_catalog(tmp_path, edition=TAG)
    write_digests(write_edition_files(catalog))
    sample_dir = catalog / "core/eval_samples/review/pinned"
    return catalog, load_task_sample(sample_dir, source_package=ENGINE)


def test_an_edition_renders_its_frozen_prompt_and_included_rule(tmp_path: Path) -> None:
    catalog, sample = _pinned(tmp_path)

    text = render_prompt(sample, strict=True, edition=load_edition(catalog / "editions" / TAG))

    assert text.startswith(FROZEN_PROMPT_BODY)
    assert FROZEN_RULE_BODY.strip() in text
    assert CURRENT_PROMPT_BODY.strip() not in text


def test_an_edition_ignores_a_local_rule_override(tmp_path: Path) -> None:
    catalog, sample = _pinned(tmp_path)
    write_local_rule_override(catalog)

    head = render_prompt(sample, strict=True)
    frozen = render_prompt(sample, strict=True, edition=load_edition(catalog / "editions" / TAG))

    assert OVERRIDE_RULE_BODY.strip() in head
    assert OVERRIDE_RULE_BODY.strip() not in frozen
    assert FROZEN_RULE_BODY.strip() in frozen


def test_a_prompt_the_edition_lacks_is_unscorable_even_for_a_lenient_runner(
    tmp_path: Path,
) -> None:
    catalog, sample = _pinned(tmp_path)
    sample.prompt_id = "explain"

    with pytest.raises(PromptResolutionError, match="no prompt 'explain'"):
        render_prompt(sample, strict=False, edition=load_edition(catalog / "editions" / TAG))
