"""The catalog reference pages, rendered from hand-built records (docs/_ext/catalog_pages.py).

Exact-text tests pin the Markdown the site shows over :mod:`tests.docs.catalog_samples`;
the real catalog is covered in ``test_catalog_snapshot.py``.
"""

from __future__ import annotations

from catalog_pages import GENERATED_NOTE, render_pages
from catalog_snapshot import CatalogSnapshot, RuleEntry, SectionEntry, SkillEntry
from tests.docs.catalog_samples import SAMPLE_SNAPSHOT, SAMPLE_TREE_URL


def _pages() -> dict[str, str]:
    return render_pages(SAMPLE_SNAPSHOT, source_tree_url=SAMPLE_TREE_URL)


def test_render_pages_writes_one_page_per_skill_and_plugin_plus_three() -> None:
    pages = _pages()

    assert sorted(pages) == [
        "hooks.md",
        "index.md",
        "plugins/demo_skills.md",
        "prompts.md",
        "skills/python-testing.md",
    ]
    assert all(text.startswith(GENERATED_NOTE + "\n\n") for text in pages.values())


def test_skill_page_lists_facts_sections_rules_and_references() -> None:
    page = _pages()["skills/python-testing.md"]

    assert (
        page
        == "\n\n".join(
            [
                GENERATED_NOTE,
                "# python-testing",
                "Guides how tests are written.",
                ":Use when: writing tests\n"
                ":Covers: Test files\n"
                f":Source: [`catalog/core/skills/python-testing`]({SAMPLE_TREE_URL}catalog/core/skills/python-testing)",
                "## Mocking",
                "Double only what you do not own.",
                ":Impact: CRITICAL\n:Open when: A test replaces a collaborator.",
                "| Rule | What it says |\n| --- | --- |\n| Prefer fakes (`fakes`) | Use a \\| named fake. |",
                "## Other",
                "| Rule | What it says |\n| --- | --- |\n| X rule (`x`) (from `acme.rules`) | Says x. |",
                "## References and examples",
                "| Path | Open when |\n| --- | --- |\n| `references/doubles.md` | Choosing a double. |",
            ]
        )
        + "\n"
    )


def test_plugin_page_has_credit_how_to_enable_capabilities_and_skills() -> None:
    page = _pages()["plugins/demo_skills.md"]

    assert "# demo_skills\n\nPlan and test (Demo skills).\n\nVendored from Demo (MIT)." in page
    assert ":Framework name: `demo`" in page
    assert ':Turn it on: `framework = "demo"` in `.coding-agent-playbook.toml`, ' in page
    assert "`playbook init --framework demo`" in page
    assert "### grill\n\nInterview the user.\n\n:Capabilities: clarify\n:Source: " in page
    assert "| `clarify` | [grill](#grill) |" in page
    assert "## Always rules" in page
    assert "| Tracker (`tracker`) | Track tickets. |" in page
    assert page.index("## Skills") < page.index("### grill")


def test_prompts_page_gives_each_prompt_its_slash_command() -> None:
    page = _pages()["prompts.md"]

    assert "| Review | `/review` | Review the change. |\n" in page
    assert "Prompt sets" not in page


def test_hooks_page_orders_families_like_the_hooks_guide_then_new_ones() -> None:
    page = _pages()["hooks.md"]

    headings = [line for line in page.splitlines() if line.startswith("## ")]
    assert headings == ["## Protect the playbook", "## Audit", "## Zeta"]
    assert (
        "| Guard (`guard`) | Guard the lockfile. | `pre_tool_use`, `stop` | default "
        "| claude_code, opencode |"
    ) in page


def test_index_page_tables_link_and_its_toctree_lists_every_page() -> None:
    page = _pages()["index.md"]

    assert "| [python-testing](skills/python-testing.md) | Guides how tests are written. |" in page
    assert "| [demo_skills](plugins/demo_skills.md) | Plan and test (Demo skills). |" in page
    assert "| Project context (`project-context`) | Read the glossary. |" in page
    assert page.endswith(
        "```{toctree}\n:hidden:\n\nskills/python-testing\nplugins/demo_skills\nprompts\nhooks\n```\n"
    )


def test_table_cells_are_flattened_to_one_line() -> None:
    skill = SkillEntry(
        "s",
        "d",
        "p",
        sections=(SectionEntry("T", "", "", "", (RuleEntry("r", "R", "two\nlines"),)),),
    )
    snapshot = CatalogSnapshot((skill,), (), (), (), ())

    page = render_pages(snapshot, source_tree_url=SAMPLE_TREE_URL)["skills/s.md"]

    assert "| R (`r`) | two lines |" in page


def test_without_a_source_host_source_paths_are_shown_unlinked() -> None:
    page = render_pages(SAMPLE_SNAPSHOT, source_tree_url="")["skills/python-testing.md"]

    assert ":Source: `catalog/core/skills/python-testing`" in page
