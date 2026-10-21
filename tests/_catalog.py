"""Where the catalog (the shipped content) lives in this checkout, for tests that pin it by path.

The catalog roots are anchored on the checkout (``REPO_ROOT / "catalog"``), not
on the production resolver, so path pins stay independent of the code under
test: a resolver bug cannot carry a test's expectations along with it. The one
exception is ``PRECOMMIT_TEMPLATE_DIR``: it is engine wiring, not content, and is
computed through the imported package with ``importlib.resources``. Tests import
their roots from here, so a change to the catalog layout edits this one module.
"""

from __future__ import annotations

import tempfile
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.catalog._skill_rules import declared_skill_id, find_skill_md
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from coding_agent_playbook.catalog.source import FileSystemArtifactSource, _iter_skills
from coding_agent_playbook.skills.membership import is_rule_skill
from coding_agent_playbook.skills.naming import skill_id_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.artifacts.skill import Skill

#: The repository checkout this test suite runs from.
REPO_ROOT: Path = Path(__file__).resolve().parents[1]
#: The checkout's catalog: ``README.md``, ``core/`` and ``plugins/``.
CATALOG_ROOT: Path = REPO_ROOT / "catalog"
#: The engine's core layer: ``ATTRIBUTIONS.md``, ``eval_samples/``, ``hooks/``, ``prompts/``,
#: ``rules/`` and ``skills/``.
CORE_ROOT: Path = CATALOG_ROOT / "core"
#: The parent of every bundled plugin's directory.
PLUGINS_ROOT: Path = CATALOG_ROOT / "plugins"
#: The pre-commit template's directory. It is engine wiring, not content, so it
#: stays inside the package and resolves through the imported package rather
#: than ``REPO_ROOT``: it must ship wherever the engine's code does.
PRECOMMIT_TEMPLATE_DIR: Path = Path(
    str(resources.files("coding_agent_playbook") / "templates" / "precommit")
)
#: Rule id -> its core skill, for the ids hooks (``linked_rule``) and prompts
#: (``includes_rules``) depend on: a split keeps them on the piece with the old topic (prU D21).
KEPT_RULE_IDS: Final[Mapping[str, str]] = {
    "python-typing": "python-coding",
    "python-error-handling": "python-coding",
    "python-docstrings": "python-coding",
    "python-dependency-injection": "python-coding",
    "python-pure-core": "python-coding",
    "pytest": "python-testing",
    "ml-serialization-security": "ml-data",
}
#: Rule id -> the core skill it belonged to, for the ids prU retires (D21).
RETIRED_RULE_IDS: Final[Mapping[str, str]] = {
    "python-performance-idioms": "python-coding",
    "python-classes-and-protocols": "python-coding",
    "ml-dtypes-and-typing": "ml-data",
    "ml-reproducibility-and-testing": "ml-data",
}


def bundled_plugin_dirs() -> list[Path]:
    """Return every directory directly under :data:`PLUGINS_ROOT`, sorted.

    Catalog gates iterate this listing rather than naming plugins, so a new
    ``catalog/plugins/<name>/`` is gated with no test edit (acceptance 5). It is
    not filtered by the leaf rule: a misnamed directory is still scanned, and the
    leaf-rule guard in ``test_catalog_layout.py`` fails on its name.

    Example::

        [path.name for path in bundled_plugin_dirs()]  # ['mattpocock_skills', 'superpowers']
    """
    return sorted(entry for entry in PLUGINS_ROOT.iterdir() if entry.is_dir())


def plugin_root(name: str) -> Path:
    """Return bundled plugin *name*'s layer root, the directory holding ``skills/``.

    Example::

        plugin_root("superpowers") / "skills" / "brainstorming"
    """
    return PLUGINS_ROOT / name


def plugin_files_root(name: str) -> Path:
    """Return bundled plugin *name*'s top directory, holding ``LICENSE`` and ``ATTRIBUTIONS.md``.

    Since the move to ``catalog/plugins/<name>/`` this is the same directory as
    :func:`plugin_root`: the root files sit next to ``skills/``.

    Example::

        plugin_files_root("superpowers") / "ATTRIBUTIONS.md"
    """
    return PLUGINS_ROOT / name


def bundled_eval_sample_roots() -> list[Path]:
    """Every bundled layer's ``eval_samples/`` dir: core first, then each plugin that ships one.

    Eval samples are a per-layer artifact kind, so a plugin may ship its own;
    the shipped-sample gates walk all of them.

    Example: ``bundled_eval_sample_roots()[0] == CORE_ROOT / "eval_samples"``.
    """
    plugin_roots = [d / "eval_samples" for d in bundled_plugin_dirs()]
    return [CORE_ROOT / "eval_samples", *(r for r in plugin_roots if r.is_dir())]


def core_markdown_sources(kind: str) -> list[Path]:
    """Every ``.md`` and ``.md.j2`` source under ``CORE_ROOT / kind``, at any depth, sorted.

    Raises ``FileNotFoundError`` naming the directory when core has no such kind,
    so a gate never iterates an empty listing by mistake.

    Example: ``core_markdown_sources("prompts")[0].name`` -> ``"characterize.md"``.
    """
    root = CORE_ROOT / kind
    if not root.is_dir():
        raise FileNotFoundError(f"core has no {kind!r} directory at {root}")
    return sorted(p for p in root.rglob("*") if p.name.endswith((".md", ".md.j2")))


def core_rule_paths() -> list[tuple[str | None, Path]]:
    """``(home skill, path)`` for every core rule source, ``rules/`` first, then each skill's.

    Walks ``CORE_ROOT / "rules"`` (home ``None``) and ``CORE_ROOT / "skills/<dir>/rules"``
    for each skill dir holding ``SKILL.md`` or ``SKILL.md.j2`` (home: the id that
    file declares), the layout the loader reads (prU D5). The file walk is this
    module's own, so a loader bug cannot hide a rule; only the skill-file names
    and the id lookup are shared. One walker, so a rule moved into its skill
    stays visible to every catalog gate.

    Example: ``core_rule_paths()[0]`` -> ``(None, CORE_ROOT / "rules/always/00-....md.j2")``.
    """
    rules: list[tuple[str | None, Path]] = [(None, p) for p in core_markdown_sources("rules")]
    for skill_dir in sorted(p for p in (CORE_ROOT / "skills").iterdir() if p.is_dir()):
        rules_dir = skill_dir / "rules"
        skill_md = find_skill_md(skill_dir)
        if not rules_dir.is_dir() or skill_md is None:
            continue
        found = sorted(p for p in rules_dir.rglob("*") if p.name.endswith((".md", ".md.j2")))
        rules.extend((declared_skill_id(skill_md), path) for path in found)
    return rules


def core_rules() -> dict[str, Rule]:
    """Every core rule (:func:`core_rule_paths`), parsed from its file, by id.

    Read from the checkout, not through the artifact source, so a loader bug
    cannot hide a shipped rule from the catalog gates. A rule in a skill's
    ``rules/`` gets that skill as ``home_skill``, which fills ``skill`` when the
    file leaves it out, as the loader does.

    Example: ``core_rules()["python-typing"].frontmatter.skill`` -> ``"python-coding"``.
    """
    rules = (
        Rule.from_markdown(path, ENGINE_PACKAGE, home_skill=home)
        for home, path in core_rule_paths()
    )
    return {rule.frontmatter.id: rule for rule in rules}


def core_skills(skills_root: Path = CORE_ROOT / "skills") -> list[Skill]:
    """Every skill under ``skills_root`` (core's by default), loaded as sync loads it, by directory.

    The skills counterpart of :func:`core_rules`: anchored on the checkout, but
    parsed by the engine's own skill walker, so a ``SKILL.md.j2`` skill counts
    exactly as sync would count it.

    Example: ``[skill.frontmatter["id"] for skill in core_skills()][0]`` -> ``"ml-data"``.
    """
    return list(_iter_skills(skills_root, ENGINE_PACKAGE))


def core_skill_ids() -> frozenset[str]:
    """The ids of the skills core ships: the directories under ``CORE_ROOT / "skills"``.

    Every synthetic sync writes the core skills whose member rules apply, next to
    a test's own skill, so a test that pins a whole skills root allows these.

    Example: ``"python-coding" in core_skill_ids()`` -> ``True``.
    """
    return frozenset(path.name for path in (CORE_ROOT / "skills").iterdir() if path.is_dir())


def core_rule_skill_ids() -> list[str]:
    """The sorted ids of the core skills that take member rules: a ``playbook:`` block (E6).

    Validation's V1 and V5 messages list exactly these as the known skills, so
    tests build those strings here instead of spelling the skills out. The list
    goes through the engine's own discovery (``list_skills``, ``is_rule_skill``,
    ``skill_id_of``) so the expectation cannot drift from what the engine lists;
    the throwaway repo root holds no repo-local skills, so only core's count.

    Example: ``", ".join(core_rule_skill_ids())`` -> ``"ml-data, python-coding, ..."``.
    """
    with tempfile.TemporaryDirectory() as repo_root:
        skills = FileSystemArtifactSource(repo_root=Path(repo_root)).list_skills()
        return sorted(
            skill_id_of(skill)
            for skill in skills
            if skill.source_package == ENGINE_PACKAGE and is_rule_skill(skill)
        )
