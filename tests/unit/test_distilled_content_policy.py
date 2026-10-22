"""The import policy for vendored core content (ADR 0004; specs/prS-skills-context.md 9.9, 9.15).

Core copies the upstream Python guidance and adapts it (ADR 0004, D1), leaving out
what the import policy drops: the tool and dependency recommendations the engine
does not adopt, and the upstream conventions an existing core rule overrides.
These gates keep a dropped recommendation from creeping back into a rule,
reference, SKILL.md or prompt, an insecure setting (D78(4)) out of every rule and
reference, and each moved topic in one owner rule. Provenance is
``tests/integration/test_core_attributions.py``'s job; the sources' own names are
the marker regex's (``tests/integration/test_resources_self_contained.py``).
"""

from __future__ import annotations

import re
from pathlib import PurePath
from typing import TYPE_CHECKING, Final

import pytest

from tests._attributions import write_tree
from tests._budget_probe import reference_probe_facts, render_core_rule
from tests._catalog import (
    CORE_ROOT,
    CORE_SKILLS_ROOT,
    core_markdown_sources,
    core_rule_paths,
    core_rules,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

pytestmark = pytest.mark.catalog

#: Recommendations D8 drops: a build backend, three new test dependencies, letting
#: mypy install packages, piping a download into a shell, and silencing a whole
#: warning category (spec 9.5.1, item 8). A literal substring scan, so a
#: prohibition must avoid the token too.
DROPPED_RECOMMENDATIONS: Final = (
    "hatchling",
    "factory_boy",
    "pytest-randomly",
    "pytest-check",
    "--install-types",
    "| sh",
    "ignore::DeprecationWarning",
)
#: Insecure settings no rule or reference may show, not even in a Bad Example
#: (D78(4)): Flask's debugger, Streamlit's CORS and XSRF protection switched off, and
#: its usage telemetry switched on. Case-insensitive; ``=``, ``:`` or a space may
#: separate the key from its value, so the TOML, CLI and environment forms all match.
INSECURE_SETTINGS: Final = (
    re.compile(r"(?i)\bdebug\s*=\s*True\b"),
    re.compile(r"(?i)\bFLASK_DEBUG\s*=\s*[\"']?1\b"),
    re.compile(r"(?i)\benableCORS[\"']?\s*[=:\s]\s*[\"']?false\b"),
    re.compile(r"(?i)\benableXsrfProtection[\"']?\s*[=:\s]\s*[\"']?false\b"),
    re.compile(r"(?i)\bgatherUsageStats[\"']?\s*[=:\s]\s*[\"']?true\b"),
)
#: A topic that changed owner (spec 9.4.7, prU D46(1)) -> the one core rule whose body holds it.
MOVED_GUIDANCE_OWNERS: Final = (
    ("composition over inheritance", "design-composition-over-inheritance"),
    ("slots=True", "python-data-shapes"),
    ("monkeypatch.setenv", "pytest-monkeypatch"),
    ("from conftest import", "pytest-conftest"),
    # The engine's skip/xfail line keeps its characterization sentence through the
    # C-python-testing-01 split (review of #247).
    ("quirks included", "pytest"),
)
#: A D46(1) owner a content lane has not created yet -> the pin that holds until it
#: ships, and that lane. The lane that creates the owner deletes its row here
#: (tickets.md, content-ticket template step 1), and
#: ``test_pending_owners_are_not_shipped_yet`` fails until it does.
PENDING_OWNERS: Final[Mapping[str, tuple[str, str, str]]] = {
}
#: The ``generate-tests`` prompt's line on doubles (spec H18): named fakes come first (D8).
_GENERATE_TESTS_PROMPT: Final = CORE_ROOT / "prompts" / "generate-tests.md.j2"


def policy_sources(core_root: Path = CORE_ROOT) -> list[Path]:
    """Every markdown source an agent reads as guidance, sorted: the always rules, every
    ``.md``/``.md.j2`` under a core skill (SKILL.md, rules, references, examples) and
    the prompts. The license copies carry no ``.md`` suffix, so they stay out (D58).
    """
    kinds = ("prompts", "rules", CORE_SKILLS_ROOT.name)
    return sorted(path for kind in kinds for path in core_markdown_sources(kind, core_root))


def is_rule_or_reference(rel: PurePath) -> bool:
    """True for a rule (always or a skill's) or a skill reference, relative to core (D78(4)).

    >>> is_rule_or_reference(PurePath("skills/s/references/guide.md"))
    True
    >>> is_rule_or_reference(PurePath("skills/s/SKILL.md"))
    False
    """
    parts = rel.parts
    in_skill = len(parts) > 3 and parts[0] == CORE_SKILLS_ROOT.name
    return parts[0] == "rules" or (in_skill and parts[2] in ("rules", "references"))


def insecure_setting_sources(core_root: Path = CORE_ROOT) -> list[Path]:
    """The policy sources the D78(4) insecure-settings scan reads: rules and references."""
    return [
        path
        for path in policy_sources(core_root)
        if is_rule_or_reference(PurePath(path.relative_to(core_root)))
    ]


_SCANNED_SOURCES: Final = policy_sources()


@pytest.mark.parametrize("token", DROPPED_RECOMMENDATIONS)
@pytest.mark.parametrize(
    "path", _SCANNED_SOURCES, ids=lambda p: p.relative_to(CORE_ROOT).as_posix()
)
def test_core_artifacts_omit_dropped_recommendations(path: Path, token: str) -> None:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(CORE_ROOT).as_posix()
    assert token not in text, f"{rel}: recommends {token!r}, which the D8 import policy drops"


@pytest.mark.parametrize(
    "path", insecure_setting_sources(), ids=lambda p: p.relative_to(CORE_ROOT).as_posix()
)
def test_core_rules_and_references_show_no_insecure_setting(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(CORE_ROOT).as_posix()
    hits = [m.group(0) for pattern in INSECURE_SETTINGS for m in pattern.finditer(text)]
    assert hits == [], f"{rel}: shows insecure settings {hits} (D78(4))"


@pytest.mark.parametrize(
    "text",
    [
        "app.run(debug=True)",
        "app.run(host='0.0.0.0', debug = True)",
        "export FLASK_DEBUG=1",
        'FLASK_DEBUG="1"',
        "enableCORS = false",
        "streamlit run app.py --server.enableCORS false",
        "--server.enableXsrfProtection=false",
        "gatherUsageStats = true",
        "--browser.gatherUsageStats=true",
    ],
)
def test_insecure_settings_match(text: str) -> None:
    assert any(pattern.search(text) for pattern in INSECURE_SETTINGS), text


@pytest.mark.parametrize(
    "text",
    [
        "app.run(debug=False)",
        "debug=True_value_name",
        "FLASK_DEBUG=0",
        "enableCORS = true",
        "enableXsrfProtection = true",
        "gatherUsageStats = false",
    ],
)
def test_safe_settings_do_not_match(text: str) -> None:
    assert not any(pattern.search(text) for pattern in INSECURE_SETTINGS), text


def test_policy_scan_covers_every_core_rule_skill_and_prompt() -> None:
    """Guard against a walker that silently scans fewer files than core ships."""
    kinds = {path.relative_to(CORE_ROOT).parts[0] for path in _SCANNED_SOURCES}
    assert kinds == {"rules", "skills", "prompts"}, kinds
    expected = {path for _, path in core_rule_paths()} | set(core_markdown_sources("prompts"))
    expected |= set(CORE_SKILLS_ROOT.glob("*/SKILL.md"))
    unscanned = expected - set(_SCANNED_SOURCES)
    assert not unscanned, (
        f"core sources missing from the policy scan: {sorted(map(str, unscanned))}"
    )
    assert {rule.source_path for rule in core_rules().values()} <= set(_SCANNED_SOURCES)


#: A synthetic core tree: one file of every kind the policy scans or skips.
_SYNTHETIC_CORE: Final = (
    "rules/always/r.md",
    "skills/s/SKILL.md",
    "skills/s/rules/a.md.j2",
    "skills/s/references/guide.md",
    "skills/s/references/LICENSE.python-best-practices",
    "skills/s/examples/app/README.md",
    "skills/s/scripts/tool.py",
    "prompts/p.md",
)


def test_policy_scan_reads_references_and_skips_license_copies(tmp_path: Path) -> None:
    """D58: references are scanned like rules; the byte-identical license copies are not."""
    write_tree(tmp_path, dict.fromkeys(_SYNTHETIC_CORE, "x\n"))

    scanned = [path.relative_to(tmp_path).as_posix() for path in policy_sources(tmp_path)]

    assert scanned == [
        "prompts/p.md",
        "rules/always/r.md",
        "skills/s/SKILL.md",
        "skills/s/examples/app/README.md",
        "skills/s/references/guide.md",
        "skills/s/rules/a.md.j2",
    ]


def test_insecure_setting_scan_reads_only_rules_and_references(tmp_path: Path) -> None:
    """D78(4) names rules and references; SKILL.md, prompts and examples stay out."""
    write_tree(tmp_path, dict.fromkeys(_SYNTHETIC_CORE, "x\n"))

    scanned = [p.relative_to(tmp_path).as_posix() for p in insecure_setting_sources(tmp_path)]

    assert scanned == [
        "rules/always/r.md",
        "skills/s/references/guide.md",
        "skills/s/rules/a.md.j2",
    ]


def test_core_markdown_sources_refuses_a_kind_core_does_not_ship() -> None:
    """A misspelled kind fails loudly instead of yielding a scan over nothing."""
    with pytest.raises(FileNotFoundError, match="'promts'"):
        core_markdown_sources("promts")


@pytest.mark.parametrize(("needle", "owner"), MOVED_GUIDANCE_OWNERS)
def test_moved_guidance_has_one_owner(needle: str, owner: str) -> None:
    """Case-insensitive, so a capitalized copy left behind in the old owner still fails.

    Until a content lane creates a D46(1) owner, its :data:`PENDING_OWNERS` pin holds.
    """
    if owner in PENDING_OWNERS:
        needle, owner, _lane = PENDING_OWNERS[owner]
    holders = sorted(
        rule_id
        for rule_id, rule in core_rules().items()
        if needle.casefold() in rule.body.casefold()
    )
    assert holders == [owner], f"{needle!r} must live only in {owner}; found in {holders}"


@pytest.mark.parametrize("owner", sorted(PENDING_OWNERS))
def test_pending_owners_are_not_shipped_yet(owner: str) -> None:
    """A lane that creates a D46(1) owner drops its pending row, so the final pin applies."""
    lane = PENDING_OWNERS[owner][2]
    assert owner not in core_rules(), (
        f"{owner} ships now: {lane} deletes its PENDING_OWNERS row in {__name__}"
    )


def test_every_pending_owner_is_a_moved_guidance_owner() -> None:
    assert set(PENDING_OWNERS) <= {owner for _, owner in MOVED_GUIDANCE_OWNERS}


def test_pytest_test_doubles_puts_named_fakes_first(tmp_path: Path) -> None:
    """D8: a named fake is the default double; autospec is the fallback at thin seams."""
    body = render_core_rule("pytest-test-doubles", reference_probe_facts(tmp_path))
    fake, autospec = body.find("Fake"), body.find("autospec")
    assert fake != -1 and autospec != -1, "pytest-test-doubles must name both Fake and autospec"
    assert fake < autospec, (
        f"pytest-test-doubles names autospec (offset {autospec}) before a named Fake "
        f"(offset {fake}); D8 makes named fakes the default"
    )


def test_generate_tests_prompt_recommends_named_fakes() -> None:
    """H18 / R3-4: the prompt no longer sends the agent to ``mocker`` for external services."""
    text = _GENERATE_TESTS_PROMPT.read_text(encoding="utf-8")
    assert "`mocker`" not in text, "generate-tests still recommends pytest-mock's mocker fixture"
    doubles = [line for line in text.splitlines() if "named fakes" in line]
    assert len(doubles) == 1, f"generate-tests needs one named-fakes line; got {doubles}"
    autospec = doubles[0].find("autospec")
    assert autospec > doubles[0].find("named fakes"), (
        f"generate-tests must name autospec after named fakes, as the fallback: {doubles[0]!r}"
    )


def test_docstrings_rule_keeps_the_example_contract(tmp_path: Path) -> None:
    """D8: the usage example stays required; Google-style sections stay optional."""
    body = render_core_rule("python-docstrings", reference_probe_facts(tmp_path))
    assert "usage example" in body, "python-docstrings no longer requires a usage example"
    google = [line for line in body.splitlines() if "Google" in line]
    assert google, "python-docstrings never mentions Google-style sections"
    assert all("optional" in line for line in google), (
        f"python-docstrings must call Google-style sections optional: {google}"
    )
