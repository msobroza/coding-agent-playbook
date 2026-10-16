"""Single source of truth for what the bundled ``superpowers`` plugin must ship.

The sets are hardcoded on purpose: deriving them from the on-disk tree would let
an accidentally dropped skill, script, or reference file pass every test. Shared
by the ``tests/plugins/`` suite and every other test that names the plugin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests._content import plugin_files_root

if TYPE_CHECKING:
    from pathlib import Path

#: The 15 upstream Superpowers skills (v7.0.0) vendored into the plugin.
EXPECTED_SKILL_IDS: frozenset[str] = frozenset(
    {
        "brainstorming",
        "diagnosing-superpowers",
        "dispatching-parallel-agents",
        "executing-plans",
        "finishing-a-development-branch",
        "receiving-code-review",
        "requesting-code-review",
        "subagent-driven-development",
        "systematic-debugging",
        "test-driven-development",
        "using-git-worktrees",
        "using-superpowers",
        "verification-before-completion",
        "writing-plans",
        "writing-skills",
    }
)

#: Every executable the plugin ships, as ``<skill-id>/scripts/<file>``.
EXPECTED_SCRIPTS: frozenset[str] = frozenset(
    {
        "executing-plans/scripts/task-done",
        "executing-plans/scripts/task-start",
        "subagent-driven-development/scripts/review-package",
        "subagent-driven-development/scripts/sdd-workspace",
        "subagent-driven-development/scripts/task-brief",
        "systematic-debugging/scripts/find-polluter.sh",
        "writing-skills/scripts/render-graphs.js",
    }
)

#: Non-executable files that ship next to the scripts, as ``<skill-id>/scripts/<file>``.
#: ``render-graphs.js`` is ES-module syntax that upstream parsed as ESM only through
#: its repo-root ``package.json`` (not vendored); this sidecar carries that one
#: setting so the helper runs wherever the skill is synced.
EXPECTED_SCRIPT_SUPPORT_FILES: frozenset[str] = frozenset({"writing-skills/scripts/package.json"})

#: The MIT notice copied into every skill: sync copies skill directories into
#: consumer repos, so the notice has to travel inside each one (ATTRIBUTIONS.md).
EXPECTED_LICENSE_COPIES: frozenset[str] = frozenset(
    f"{skill_id}/references/LICENSE" for skill_id in EXPECTED_SKILL_IDS
)

#: Every file under a skill's ``references/``, as ``<skill-id>/references/<path>``.
#: The port moved upstream's skill-root supporting files here, so a dropped or
#: mis-moved file must fail CI rather than surface as a dangling inline path.
EXPECTED_REFERENCE_FILES: frozenset[str] = EXPECTED_LICENSE_COPIES | frozenset(
    {
        "brainstorming/references/builder-check-prompt.md",
        "diagnosing-superpowers/references/context-safety.md",
        "diagnosing-superpowers/references/prompts/analyst-common.md",
        "diagnosing-superpowers/references/prompts/cost-and-time.md",
        "diagnosing-superpowers/references/prompts/plan-adherence.md",
        "diagnosing-superpowers/references/prompts/quality-evidence.md",
        "diagnosing-superpowers/references/prompts/repeated-work.md",
        "diagnosing-superpowers/references/prompts/request-conflicts.md",
        "diagnosing-superpowers/references/prompts/scrub-audit.md",
        "diagnosing-superpowers/references/prompts/scrub.md",
        "diagnosing-superpowers/references/prompts/similar-session.md",
        "diagnosing-superpowers/references/prompts/skill-timeline.md",
        "diagnosing-superpowers/references/prompts/stumbles.md",
        "diagnosing-superpowers/references/redaction-policy.md",
        "diagnosing-superpowers/references/session-discovery.md",
        "diagnosing-superpowers/references/templates/bundle-README.md",
        "diagnosing-superpowers/references/templates/case.md",
        "diagnosing-superpowers/references/templates/report.md",
        "requesting-code-review/references/code-reviewer.md",
        "subagent-driven-development/references/implementer-prompt.md",
        "subagent-driven-development/references/re-review-prompt.md",
        "subagent-driven-development/references/task-reviewer-prompt.md",
        "systematic-debugging/references/CREATION-LOG.md",
        "systematic-debugging/references/condition-based-waiting-example.ts",
        "systematic-debugging/references/condition-based-waiting.md",
        "systematic-debugging/references/defense-in-depth.md",
        "systematic-debugging/references/root-cause-tracing.md",
        "systematic-debugging/references/test-academic.md",
        "systematic-debugging/references/test-pressure-1.md",
        "systematic-debugging/references/test-pressure-2.md",
        "systematic-debugging/references/test-pressure-3.md",
        "test-driven-development/references/writing-good-tests.md",
        "using-superpowers/references/antigravity-tools.md",
        "using-superpowers/references/claude-code-tools.md",
        "using-superpowers/references/codex-tools.md",
        "using-superpowers/references/gemini-tools.md",
        "using-superpowers/references/hermes-tools.md",
        "using-superpowers/references/muse-tools.md",
        "using-superpowers/references/pi-tools.md",
        "writing-skills/references/anthropic-best-practices.md",
        "writing-skills/references/examples/CLAUDE_MD_TESTING.md",
        "writing-skills/references/graphviz-conventions.dot",
        "writing-skills/references/persuasion-principles.md",
        "writing-skills/references/testing-skills-with-subagents.md",
    }
)

#: ``references/…`` / ``scripts/…`` path mentions that intentionally resolve to no
#: plugin file, keyed by the mentioning file (relative to the skills root). They
#: are illustrative examples of *some* skill's layout, or name another skill's
#: template by that skill ("subagent-driven-development's ./references/…").
UNRESOLVED_PATH_MENTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("using-superpowers/references/gemini-tools.md", "references/implementer-prompt.md"),
        ("using-superpowers/references/gemini-tools.md", "references/code-reviewer.md"),
        ("writing-skills/SKILL.md", "scripts/tool.js"),
        ("writing-skills/SKILL.md", "scripts/tool.sh"),
        ("writing-skills/references/anthropic-best-practices.md", "scripts/analyze_form.py"),
        ("writing-skills/references/anthropic-best-practices.md", "scripts/fill_form.py"),
        ("writing-skills/references/anthropic-best-practices.md", "scripts/helper.py"),
        ("writing-skills/references/anthropic-best-practices.md", "scripts/migrate.py"),
        ("writing-skills/references/anthropic-best-practices.md", "scripts/pdf_to_images.py"),
        ("writing-skills/references/anthropic-best-practices.md", "scripts/validate_boxes.py"),
        ("writing-skills/references/anthropic-best-practices.md", "scripts/validate_fields.py"),
        ("writing-skills/references/anthropic-best-practices.md", "scripts/verify_output.py"),
    }
)

#: The only skill-root entries the engine's skill sync copies (SPEC §6.3.1);
#: anything else at a skill root would be silently dropped by ``playbook sync``.
SYNCED_SKILL_ENTRIES: frozenset[str] = frozenset({"SKILL.md", "scripts", "references"})

#: The dotted name a consumer lists in ``overlays_enabled`` to turn the plugin on.
PLUGIN_NAME = "coding_agent_playbook.plugins.superpowers"

#: The plugin's directory in the checkout: ``README.md``, ``LICENSE``,
#: ``ATTRIBUTIONS.md`` and ``skills/``.
PLUGIN_ROOT: Path = plugin_files_root("superpowers")
SKILLS_ROOT: Path = PLUGIN_ROOT / "skills"

#: The native skill roots the default adapters write through the shared
#: ``SkillWriter`` (SPEC §10.8): claude_code, opencode, and the shared_skills hub.
NATIVE_SKILL_ROOTS: tuple[str, ...] = (".claude/skills", ".opencode/skills", "shared_skills")

#: The adapter list ``playbook init`` writes (``agents_md`` is always on).
DEFAULT_ADAPTERS: tuple[str, ...] = ("continue", "claude_code", "opencode", "shared_skills")


def consumer_config(*, overlays: list[str], adapters: tuple[str, ...] = DEFAULT_ADAPTERS) -> str:
    """Return a ``.coding-agent-playbook.toml`` enabling ``adapters`` (top-level keys).

    The default is the adapter set ``playbook init`` enables (``agents_md`` is
    always on), so a plugin skill lands in every :data:`NATIVE_SKILL_ROOTS` root
    and as a degraded Continue prompt. Example::

        consumer_config(overlays=[PLUGIN_NAME])  # opt the consumer into the plugin
        consumer_config(overlays=[], adapters=(*DEFAULT_ADAPTERS, "agent_harness"))
    """
    overlay_list = ", ".join(f'"{name}"' for name in overlays)
    adapter_list = ", ".join(f'"{name}"' for name in adapters)
    return (
        "schema_version = 1\n"
        f"adapters_enabled = [{adapter_list}]\n"
        f"overlays_enabled = [{overlay_list}]\n"
        "\n"
        "[project]\n"
        'name = "synthetic"\n'
        'kind = "python-library"\n'
        "\n"
        "[engine]\n"
        'version = "0.1.0a0"\n'
        "\n"
        "[storage]\n"
        'artifact_source = "filesystem"\n'
        'state_source = "filesystem"\n'
    )


def write_consumer_repo(
    repo: Path, *, overlays: list[str], adapters: tuple[str, ...] = DEFAULT_ADAPTERS
) -> Path:
    """Write a minimal consumer repo (``pyproject.toml`` + playbook config) at ``repo``.

    Usable from a module-scoped fixture, unlike the function-scoped
    ``make_synthetic_repo``. Example::

        repo = write_consumer_repo(tmp_path_factory.mktemp("consumer"), overlays=[PLUGIN_NAME])
    """
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "synthetic"\nrequires-python = ">=3.12"\ndependencies = []\n',
        encoding="utf-8",
    )
    (repo / ".coding-agent-playbook.toml").write_text(
        consumer_config(overlays=overlays, adapters=adapters), encoding="utf-8"
    )
    return repo


def pack_files() -> list[Path]:
    """Return every regular file in the plugin (``skills/``, ``README.md``,
    ``LICENSE``, ``ATTRIBUTIONS.md``), sorted, skipping ``__pycache__``.

    Example::

        assert PLUGIN_ROOT / "LICENSE" in pack_files()
    """
    return sorted(
        path
        for path in PLUGIN_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.relative_to(PLUGIN_ROOT).parts
    )


def resource_files() -> list[Path]:
    """Return every regular file under the plugin's ``skills/`` (the synced content), sorted.

    Scoped to :data:`SKILLS_ROOT` on purpose: the upstream-coupling scan runs over
    these files, and ``ATTRIBUTIONS.md`` at the plugin root names the upstream
    repository by design.

    Example::

        assert all(SKILLS_ROOT in path.parents for path in resource_files())
    """
    return sorted(path for path in SKILLS_ROOT.rglob("*") if path.is_file())
