"""Docs-consistency guard: CONTEXT.md is the project's only glossary (skills-first spec, D12).

SPEC §3 used to define the project's terms. Two glossaries drift apart, so §3 is now a
one-line pointer and ``CONTEXT.md`` at the repository root holds every definition. The
two facts only the old glossary carried now live where the spec needs them, §6.6.7 and
§10.2; ``test_docs_lifecycle_hooks_spec`` and ``test_docs_continue_hooks`` pin them. No
other part of the spec body may cite §3 for a fact, because §3 documents nothing now.

The same module pins the vocabulary those terms brought to the other docs (spec 6.8.14):
the ``skill`` rule field in SPEC §6.1, core shipping skills in SPEC §6.3, the contributor
guide's "Add a rule" step, and the README architecture block. Core ships skills since
v0.21, so no doc may still say it ships none. Prose-only: these tests read markdown, never
engine behaviour.
"""

from __future__ import annotations

import re

import pytest

from tests._catalog import CATALOG_ROOT, REPO_ROOT, TEST_FILE_GLOBS, core_rule_skill_ids
from tests._docs import USER_DOC_PAGES
from tests.unit.test_docs_lifecycle_hooks_spec import _spec_section
from tests.unit.test_docs_readme_hooks import _blocks
from tests.unit.test_docs_readme_hooks import _section as _readme_section

pytestmark = pytest.mark.catalog

_CONTEXT_MD = REPO_ROOT / "CONTEXT.md"

#: The wording the docs used while core shipped no skills (before v0.21).
_NO_SKILLS_CLAIM = re.compile(r"ships no skills|ships none")
#: The docs that describe what core ships, by repo-relative path.
_CORE_DOCS = ("README.md", "catalog/README.md", "SPEC.md", *USER_DOC_PAGES)

#: A citation of SPEC section 3: "§3" or "Section 3", but not "§3.1" or "§30".
_SECTION_3_CITATION = re.compile(r"(?:§|Section )3(?![0-9]|\.[0-9])")

#: Every term the spec's vocabulary note relies on; each needs a ``**Term**:`` entry.
_GLOSSARY_TERMS = (
    "Rule",
    "Always rule",
    "Scoped rule",
    "Member rule",
    "Skill",
    "Reference",
    "Prompt",
    "Hook",
    "Guardrail",
    "Skill nudge",
    "Eval sample",
    "Graded set",
    "Edition",
    "Pin",
    "Release metrics",
    "Always-loaded context",
    "Skill listing",
    "Context budget",
    "Skill root",
    "Engine",
    "Catalog",
    "Layer",
    "Core",
    "Bundled plugin",
    "Overlay",
    "Detector fact",
    "Detector",
    "Renderer",
    "Adapter",
    "Harness",
    "OpenCode plugin",
    "OpenCode agent",
    "Consumer repo",
    "Distilled content",
    "Vendored content",
)


def test_spec_glossary_is_a_pointer_to_context_md() -> None:
    section = _spec_section("## 3. Glossary", "## 4. Architecture overview")
    body = [line for line in section.splitlines()[1:] if line.strip()]
    assert len(body) == 1, f"SPEC §3 must be one non-empty line, found {len(body)}: {body}"
    assert "CONTEXT.md" in body[0], f"SPEC §3 must point at CONTEXT.md, found {body[0]!r}"


def test_spec_body_cites_no_fact_to_the_glossary_pointer() -> None:
    # A "(§3, ...)" citation sends the reader to a section that documents nothing: the
    # OpenCode plugin line of §2.3 did, until it named §6.6.7 and §10.6.2 instead. The
    # Changelog keeps history ("Section 3 (glossary)"), so only the body is read.
    body = _spec_section("## 1. Context", "*End of SPEC.md")
    stale = [line for line in body.splitlines() if _SECTION_3_CITATION.search(line)]
    assert not stale, f"SPEC §3 only points at CONTEXT.md; cite it or the owning section: {stale}"


@pytest.mark.parametrize("term", _GLOSSARY_TERMS)
def test_context_md_defines_term(term: str) -> None:
    entry = re.compile(rf"^\*\*{re.escape(term)}\*\*:", re.MULTILINE)
    text = _CONTEXT_MD.read_text(encoding="utf-8")
    assert entry.search(text), f"CONTEXT.md has no entry starting '**{term}**:'"


#: Terms the editions spec (#281) retired; the glossary must not define them again.
_RETIRED_TERMS = ("Prompt set", "Twin")


@pytest.mark.parametrize("term", _RETIRED_TERMS)
def test_context_md_drops_retired_term(term: str) -> None:
    entry = re.compile(rf"^\*\*{re.escape(term)}\*\*:", re.MULTILINE)
    text = _CONTEXT_MD.read_text(encoding="utf-8")
    assert not entry.search(text), f"CONTEXT.md still defines the retired term '**{term}**'"


def test_context_md_consumer_repo_avoids_target_repo() -> None:
    text = _CONTEXT_MD.read_text(encoding="utf-8")
    entry = text[text.index("**Consumer repo**:") :].split("\n\n", 1)[0]
    assert "_Avoid_: target repo" in entry, f"'Consumer repo' must avoid 'target repo': {entry!r}"


def test_spec_section_6_1_documents_the_skill_field() -> None:
    schema = _spec_section("#### 6.1.1 Frontmatter schema", "#### 6.1.2")
    assert "skill: python-coding" in schema, "SPEC §6.1.1 must list the 'skill' field"
    assert "required when scope=scoped, forbidden when scope=always" in schema
    assert "exists after the layer merge" in schema, "§6.1.1 must say the skill is merged first"
    example = _spec_section("#### 6.1.2", "#### 6.1.3")
    assert "\nskill: python-coding\n" in example, "the §6.1.2 example rule must name its skill"


def test_spec_section_6_3_says_core_ships_skills() -> None:
    section = _spec_section("### 6.3 Skills", "### 6.4 ")
    assert "python-coding" in section, "SPEC §6.3 must name the skills core ships"
    assert "ships none" not in section, "SPEC §6.3 still says core ships no skills"
    assert "#### 6.3.3 Skills with member rules" in section


def test_catalog_readme_add_a_rule_documents_skill() -> None:
    text = (CATALOG_ROOT / "README.md").read_text(encoding="utf-8")
    add_a_rule = text[text.index("## Add a rule") : text.index("## Add a prompt")]
    assert "`skill:`" in add_a_rule, "catalog/README.md 'Add a rule' must document 'skill:'"
    missing = [i for i in core_rule_skill_ids() if f"`{i}`" not in add_a_rule]
    assert not missing, f"'Add a rule' must name every core skill a rule may name: {missing}"


def test_catalog_readme_add_a_rule_lists_the_shared_test_file_globs() -> None:
    """D41 (specs/prU-core-python-skills.md): one glob set for every test-related rule."""
    text = (CATALOG_ROOT / "README.md").read_text(encoding="utf-8")
    add_a_rule = text[text.index("## Add a rule") : text.index("## Add a prompt")]
    missing = [g for g in TEST_FILE_GLOBS if f"`{g}`" not in add_a_rule]
    assert not missing, f"'Add a rule' must list the shared test-file globs: {missing}"


@pytest.mark.parametrize("doc", _CORE_DOCS)
def test_no_doc_says_core_ships_no_skills(doc: str) -> None:
    lines = (REPO_ROOT / doc).read_text(encoding="utf-8").splitlines()
    stale = [f"{n}: {line}" for n, line in enumerate(lines, 1) if _NO_SKILLS_CLAIM.search(line)]
    assert not stale, f"{doc} still says something ships no skills (core ships eight): {stale}"


def test_readme_architecture_names_skill_references() -> None:
    blocks = _blocks(_readme_section("## Architecture"), "text")
    assert blocks, "the README architecture overview is a ```text block"
    diagram = blocks[0]
    for token in ("skills/<id>/", "Where guidance lives"):
        assert token in diagram, f"README architecture block lacks {token!r}"


#: A "hook" not preceded by "pre-commit " (CONTEXT.md, Hook: avoid bare "hook" for the git kind)
#: nor by "` playbook ": an engine hook is named by its backticked id, "`<id>` playbook hook".
_BARE_HOOK = re.compile(r"(?<!pre-commit )(?<!` playbook )\bhooks?\b", re.IGNORECASE)


def test_python_documentation_says_pre_commit_hook_for_the_git_kind() -> None:
    """Every "hook" in the docs skill is a pre-commit hook or a named playbook hook."""
    skill_dir = CATALOG_ROOT / "core" / "skills" / "python-documentation"
    bare = [
        f"{path.relative_to(skill_dir).as_posix()}:{n}: {line}"
        for path in sorted(skill_dir.rglob("*.md"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _BARE_HOOK.search(line)
    ]
    assert not bare, f"say 'pre-commit hook', never a bare 'hook' (CONTEXT.md): {bare}"
