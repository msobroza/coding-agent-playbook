"""The probe helpers of ``tests/core_skill_pins`` (prU D63, D70).

Each pinned core skill is checked on one probe. The Domino and authoring probes
are each the reference probe plus one marker, so a probe emits the reference
skills and its own, never another non-reference probe's.
"""

from __future__ import annotations

import pytest

from tests.core_skill_pins import (
    ALL_PINS,
    PROBE_KINDS,
    ProbeKind,
    skills_off_probe,
    skills_on_probe,
)

pytestmark = pytest.mark.catalog


def test_each_pinned_skill_is_checked_on_exactly_one_probe() -> None:
    on_some_probe = [skill for probe in PROBE_KINDS for skill in skills_on_probe(probe)]

    assert sorted(on_some_probe) == sorted(pins.skill_id for pins in ALL_PINS)


def test_the_authoring_probe_turns_off_the_domino_skills_but_not_playbook_creator() -> None:
    off = skills_off_probe("authoring")

    assert "domino-apps" in off
    assert "playbook-creator" not in off
    assert "playbook-creator" in skills_on_probe("authoring")


def test_the_reference_probe_turns_off_every_skill_of_another_probe() -> None:
    assert skills_off_probe("reference") == skills_on_probe("domino") | skills_on_probe("authoring")


@pytest.mark.parametrize("probe", PROBE_KINDS)
def test_a_probe_keeps_its_own_and_the_reference_skills(probe: ProbeKind) -> None:
    kept = skills_on_probe(probe) | skills_on_probe("reference")

    assert not skills_off_probe(probe) & kept
