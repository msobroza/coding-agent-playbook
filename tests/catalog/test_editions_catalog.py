"""CI gate: the shipped catalog's editions and pins agree (#281 ticket 09, ADR 0012).

Offline: every pin resolves to an existing edition, every edition is pinned by
some core sample, each edition's files match its digests file, and each pinned
sample still renders to its recorded prompt digest with an unchanged sample
digest. An engine change that alters a pinned experiment fails here until the
sample is unfrozen and frozen again (``evals.edition_checks``). The checks
themselves are tested on fixture editions in ``tests/evals/test_edition_checks.py``.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.evals.edition_checks import edition_problems
from tests._catalog import CATALOG_ROOT

pytestmark = pytest.mark.catalog


def test_the_shipped_editions_and_pins_agree() -> None:
    problems = edition_problems(CATALOG_ROOT)

    assert problems == [], "\n".join(problems)
