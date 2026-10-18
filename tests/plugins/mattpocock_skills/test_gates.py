"""The shared gate of the ``mattpocock_skills`` bundled plugin, G1-G22.

specs/prT-mattpocock-skills.md section 7.1. Every check parametrises over the
skills and files present, so the gate holds from T01's two tracer skills to
T10's 26 with no edit; only T10's ``test_inventory.py`` pins the whole set.
Failure messages name the file, the line, the offending text and the shape
expected.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import sys
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands._sync_preflight import bundled_plugins, unusable_overlays
from coding_agent_playbook.commands._validate_links import check_markdown_links
from coding_agent_playbook.links import LinksConfig
from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource
from tests._catalog import REPO_ROOT
from tests.integration.test_resources_self_contained import _URL_RE as _GENERIC_URL_RE
from tests.plugins.mattpocock_skills._expectations import (
    ALLOWLIST_DIR,
    ATTRIBUTIONS_GLOBAL_SECTIONS,
    CLAUDE_ONLY_RE,
    COUPLING_RE,
    FINAL_IDS,
    GUARD_LINE,
    LICENSE_FILE_NAMES,
    LICENSE_SHA256,
    LOAD_RE,
    PER_SKILL_HEADING,
    PLUGIN_NAME,
    PLUGIN_ROOT,
    ROOT_ENTRIES,
    RULE_FILE_NAME,
    RULES_ROOT,
    SCRIPT_SHEBANG,
    SKILLS_ROOT,
    USER_INVOKED_IDS,
    AllowEntry,
    Hit,
    command_position_hits,
    hit_path,
    imposed_tool_hits,
    load_allowlist,
    placeholder,
    plugin_files,
    present_skill_ids,
    regex_hits,
    rule_files,
    scripts_of,
    skill_docs,
    skill_files,
    split_skill,
)
from tests.plugins.superpowers_expectations import SYNCED_SKILL_ENTRIES
from tests.plugins.test_superpowers_self_contained import _PATH_MENTION_RE
from tests.plugins.test_superpowers_self_contained import _URL_RE as _SUPERPOWERS_URL_RE

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SKILLS = present_skill_ids()
assert _SKILLS, f"no skills under {SKILLS_ROOT}"
_FILES = plugin_files()
_SCRIPTS = [path for skill_id in _SKILLS for path in scripts_of(skill_id)]
_SKILL_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
#: G3: the generic gate's URL forms (bare domain plus path, ``git@``) and the superpowers ones,
#: both read as bytes. Imported, not copied, so the union follows both gates.
_URL_RES = (re.compile(_GENERIC_URL_RE.pattern.encode()), _SUPERPOWERS_URL_RE)
_MODEL_INVOKED_IDS = FINAL_IDS - USER_INVOKED_IDS


def _rel(path: Path) -> str:
    return path.relative_to(PLUGIN_ROOT).as_posix()


def _command_files(skill_id: str) -> list[Path]:
    """The files G5 reads: the markdown docs and the Python scripts of one skill."""
    return [*skill_docs(skill_id), *(p for p in scripts_of(skill_id) if p.suffix == ".py")]


def _docs_and_rules(skill_id: str) -> list[Path]:
    return [*skill_docs(skill_id), *rule_files()]


def _scanned_hits(skill_id: str) -> list[Hit]:
    """Every allowlist-able hit of one skill: G4, G5 and G13."""
    return [
        *(hit for path in skill_files(skill_id) for hit in imposed_tool_hits(path)),
        *(hit for path in _command_files(skill_id) for hit in command_position_hits(path)),
        *unresolved_path_mentions(skill_id),
    ]


def _uncovered(hits: list[Hit], entries: list[AllowEntry]) -> list[str]:
    return [f"{hit}" for hit in hits if not any(entry.covers(hit) for entry in entries)]


def _with_skill_prefix(skill_id: str, lines: list[str]) -> list[str]:
    return [f"skills/{skill_id}/{line}" for line in lines]


# --- G1, G2: a usable bundled plugin with the expected root ---------------------


def test_g1_plugin_is_usable_and_adds_only_skills_and_rules(tmp_path: Path) -> None:
    assert PLUGIN_NAME in bundled_plugins()
    assert unusable_overlays([PLUGIN_NAME]) == []
    plain = FileSystemArtifactSource(repo_root=tmp_path)
    with_plugin = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[PLUGIN_NAME])
    assert len(with_plugin.list_prompts()) == len(plain.list_prompts())
    assert len(with_plugin.list_hooks()) == len(plain.list_hooks())
    assert len(with_plugin.list_eval_tasks()) == len(plain.list_eval_tasks())
    plugin_rules = [r for r in with_plugin.list_rules() if r.source_package == PLUGIN_NAME]
    assert sorted(str(r.source_path) for r in plugin_rules) == sorted(
        str(p) for p in rule_files() if p.suffix == ".md"
    )


def test_g2_plugin_root_holds_only_the_five_entries() -> None:
    entries = {p.name for p in PLUGIN_ROOT.iterdir()}
    assert entries <= ROOT_ENTRIES, f"unexpected root entries {sorted(entries - ROOT_ENTRIES)}"
    assert entries >= ROOT_ENTRIES - {"rules"}, f"missing {sorted(ROOT_ENTRIES - entries)}"
    if RULES_ROOT.is_dir():
        assert [p.name for p in RULES_ROOT.iterdir()] == [RULE_FILE_NAME]


# --- G3-G8: self-containment ----------------------------------------------------


@pytest.mark.parametrize("path", _FILES, ids=_rel)
def test_g3_no_url_in_any_plugin_file(path: Path) -> None:
    hits = [
        f"{_rel(path)}:{number}: {match.group(0)!r}"
        for number, line in enumerate(path.read_bytes().split(b"\n"), 1)
        for pattern in _URL_RES
        for match in pattern.finditer(line)
    ]
    assert hits == [], "no URL of any form (D4); write link text as plain text"


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g4_no_imposed_tool_name(skill_id: str) -> None:
    hits = [hit for path in skill_files(skill_id) for hit in imposed_tool_hits(path)]
    assert _with_skill_prefix(skill_id, _uncovered(hits, load_allowlist(skill_id))) == [], (
        "an imposed tool (D2): remove it, or allowlist project toolchain (section 7.4)"
    )


def test_g4_no_imposed_tool_name_in_rules() -> None:
    assert [str(hit) for path in rule_files() for hit in imposed_tool_hits(path)] == []


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g5_no_ambiguous_word_in_command_position(skill_id: str) -> None:
    hits = [hit for path in _command_files(skill_id) for hit in command_position_hits(path)]
    assert _with_skill_prefix(skill_id, _uncovered(hits, load_allowlist(skill_id))) == [], (
        "a word run as a command (section 7.3): remove it, or allowlist project toolchain"
    )


def test_g5_no_ambiguous_word_in_command_position_in_rules() -> None:
    assert [str(hit) for path in rule_files() for hit in command_position_hits(path)] == []


@pytest.mark.parametrize("path", _FILES, ids=_rel)
def test_g6_no_shell_script_and_only_python3_shebangs_in_scripts(path: Path) -> None:
    assert path.suffix not in {".sh", ".bash"}, f"{_rel(path)}: a bash script (D22)"
    first = path.read_bytes().split(b"\n", 1)[0]
    if not first.startswith(b"#!"):
        return
    assert first == SCRIPT_SHEBANG.encode(), f"{_rel(path)}: shebang {first!r}"
    assert path.parent.name == "scripts" and path.suffix == ".py", f"{_rel(path)}: not a script"


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g7_no_claude_only_name(skill_id: str) -> None:
    hits = [
        str(hit) for path in _docs_and_rules(skill_id) for hit in regex_hits(path, CLAUDE_ONLY_RE)
    ]
    assert hits == [], "name the harness capability with a fallback instead (D17)"


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g8_no_coupling_marker(skill_id: str) -> None:
    files = [*skill_files(skill_id), *rule_files()]
    hits = [str(hit) for path in files for hit in regex_hits(path, COUPLING_RE)]
    assert hits == [], "text that only works with an upstream plugin install (D2)"


# --- G9-G12: layout, licence and frontmatter ------------------------------------


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g9_skill_dir_holds_only_synced_entries(skill_id: str) -> None:
    entries = {p.name for p in (SKILLS_ROOT / skill_id).iterdir()}
    assert "SKILL.md" in entries
    assert entries <= SYNCED_SKILL_ENTRIES, (
        f"sync would drop {sorted(entries - SYNCED_SKILL_ENTRIES)}"
    )
    references = [
        p for p in skill_files(skill_id) if p.relative_to(SKILLS_ROOT).parts[1] == "references"
    ]
    odd = [
        hit_path(p) for p in references if p.suffix != ".md" and p.name not in LICENSE_FILE_NAMES
    ]
    assert odd == [], "references/ holds only .md files and the licence files"


def test_g10_root_license_has_the_pinned_digest() -> None:
    digest = hashlib.sha256((PLUGIN_ROOT / "LICENSE").read_bytes()).hexdigest()
    assert digest == LICENSE_SHA256, "LICENSE must stay upstream v1.3.1's file, byte for byte"


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g10_every_skill_ships_a_byte_identical_license(skill_id: str) -> None:
    copy = SKILLS_ROOT / skill_id / "references" / "LICENSE"
    assert copy.is_file(), f"skills/{skill_id}/references/LICENSE is missing (D4)"
    assert copy.read_bytes() == (PLUGIN_ROOT / "LICENSE").read_bytes()


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g11_id_first_and_identity_and_description(skill_id: str) -> None:
    lines = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8").split("\n")
    assert lines[:2] == ["---", f"id: {skill_id}"], (
        f"first frontmatter line must be 'id: {skill_id}'"
    )
    frontmatter, _ = split_skill(skill_id)
    assert frontmatter.get("id") == frontmatter.get("name") == skill_id
    assert _SKILL_ID_RE.match(skill_id) and len(skill_id) <= 64
    description = frontmatter.get("description")
    assert isinstance(description, str) and 1 <= len(description) <= 1024


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g12_no_playbook_block(skill_id: str) -> None:
    assert "playbook" not in split_skill(skill_id)[0], "a plugin skill is never a rule skill (D11)"


def test_g12_no_jinja_template_anywhere() -> None:
    assert [_rel(p) for p in _FILES if p.suffix == ".j2"] == []


# --- G13-G16: references, loads, guard line and glossary fallback ---------------


def unresolved_path_mentions(skill_id: str) -> list[Hit]:
    """G13: ``references/…``/``scripts/…`` mentions that resolve neither in the skill
    nor, with a ``../<id>/`` prefix, in a sibling skill present in the plugin."""
    hits: list[Hit] = []
    for path in skill_docs(skill_id):
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for match in _PATH_MENTION_RE.finditer(line):
                owner = match.group("skill") or skill_id
                if not (SKILLS_ROOT / owner / match.group("path")).exists():
                    hits.append(Hit(hit_path(path), number, match.group(0), match.span(), line))
    return hits


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g13_path_mentions_resolve(skill_id: str) -> None:
    uncovered = _uncovered(unresolved_path_mentions(skill_id), load_allowlist(skill_id))
    assert _with_skill_prefix(skill_id, uncovered) == [], "a path mention that resolves nowhere"


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g14_every_load_names_a_model_invoked_final_id(skill_id: str) -> None:
    hits = [hit for path in _docs_and_rules(skill_id) for hit in regex_hits(path, LOAD_RE)]
    targets = {str(hit): LOAD_RE.fullmatch(hit.text) for hit in hits}
    bad = [
        where for where, m in targets.items() if m is None or m.group(1) not in _MODEL_INVOKED_IDS
    ]
    assert bad == [], f"a load must name one of {sorted(_MODEL_INVOKED_IDS)}"


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g15_guard_line_exactly_on_user_invoked_skills(skill_id: str) -> None:
    frontmatter, body = split_skill(skill_id)
    user_invoked = skill_id in USER_INVOKED_IDS
    assert (frontmatter.get("disable-model-invocation") is True) == user_invoked
    text = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
    if not user_invoked:
        assert GUARD_LINE not in text, "the D19 guard is for user-invoked skills only"
        return
    first = next(line for line in body.split("\n") if line.strip())
    assert first == GUARD_LINE, f"first body line is {first!r}, expected the D19 guard"
    assert text.count(GUARD_LINE) == 1
    assert GUARD_LINE not in str(frontmatter.get("description"))


@pytest.mark.parametrize("path", _FILES, ids=_rel)
def test_g16_glossary_names_carry_the_context_fallback(path: Path) -> None:
    text = path.read_bytes()
    if b"GLOSSARY.md" in text:
        assert b"CONTEXT.md" in text, f"{_rel(path)} names GLOSSARY.md without CONTEXT.md (D21)"
    if b"GLOSSARY-MAP.md" in text:
        assert b"CONTEXT-MAP.md" in text, f"{_rel(path)}: GLOSSARY-MAP.md without CONTEXT-MAP.md"


# --- G17, G18: the per-file allowlist -------------------------------------------


def test_g17_one_allowlist_file_per_present_skill() -> None:
    names = sorted(p.name for p in ALLOWLIST_DIR.iterdir())
    assert names == [f"{skill_id}.txt" for skill_id in _SKILLS]
    for skill_id in _SKILLS:
        load_allowlist(skill_id)  # raises with the file and line on a malformed entry


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_g18_every_allowlist_entry_covers_a_hit(skill_id: str) -> None:
    hits = _scanned_hits(skill_id)
    stale = [e for e in load_allowlist(skill_id) if not any(e.covers(hit) for hit in hits)]
    assert [f"{e.source}: {e.path}: {e.excerpt}" for e in stale] == [], "stale allowlist entry"


# --- G19: scripts ---------------------------------------------------------------


@pytest.mark.parametrize("script", _SCRIPTS, ids=_rel)
def test_g19_script_is_an_executable_python3_program(script: Path) -> None:
    assert script.read_text(encoding="utf-8").split("\n", 1)[0] == SCRIPT_SHEBANG
    if os.name != "nt":  # Windows has no executable bit to check
        assert os.access(script, os.X_OK), f"{_rel(script)} is not executable (mode 100755)"


@pytest.mark.parametrize("script", _SCRIPTS, ids=_rel)
def test_g19_script_parses_as_310_and_imports_only_stdlib(script: Path) -> None:
    tree = ast.parse(
        script.read_text(encoding="utf-8"), filename=str(script), feature_version=(3, 10)
    )
    assert script.name in (ast.get_docstring(tree) or ""), "the docstring must carry a usage line"
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append("." * node.level + (node.module or ""))
    assert sorted(n for n in imported if n.split(".")[0] not in sys.stdlib_module_names) == []


@pytest.fixture(scope="module")
def mypy_workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A neutral cwd + empty config + shared cache, so the repo config never applies."""
    workdir = tmp_path_factory.mktemp("mypy-scripts")
    (workdir / "mypy.ini").write_text("[mypy]\n", encoding="utf-8")
    return workdir


@pytest.mark.parametrize("script", _SCRIPTS, ids=_rel)
def test_g19_script_passes_strict_mypy_for_python_310(script: Path, mypy_workdir: Path) -> None:
    command = [sys.executable, "-m", "mypy", "--strict", "--python-version", "3.10"]
    command += ["--config-file", str(mypy_workdir / "mypy.ini")]
    command += ["--cache-dir", str(mypy_workdir / "cache"), str(script)]
    proc = subprocess.run(
        command, cwd=mypy_workdir, capture_output=True, text=True, timeout=300, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# --- G20-G22: ruff scope, links and ATTRIBUTIONS.md -----------------------------


def _glob_matches(pattern: str, path: str) -> bool:
    """Whether a ruff ``extend-exclude`` entry excludes the POSIX ``path``."""
    if not any(char in pattern for char in "*?["):
        return path == pattern or path.startswith(pattern.rstrip("/") + "/")
    regex = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*")
    regex = regex.replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    return (
        re.fullmatch(regex, path) is not None
        or re.fullmatch(regex, path.rsplit("/", 1)[-1]) is not None
    )


def test_g20_ruff_excludes_the_vendored_markdown_but_not_the_scripts() -> None:
    table = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "ruff"
    ]
    globs: list[str] = table["extend-exclude"]
    assert "catalog/plugins/mattpocock_skills/**/*.md" in globs
    assert table["force-exclude"] is True
    assert _glob_matches(
        "catalog/plugins/mattpocock_skills/**/*.md",
        "catalog/plugins/mattpocock_skills/skills/x/SKILL.md",
    )
    probe = "catalog/plugins/mattpocock_skills/skills/wizard/scripts/wizard_template.py"
    scripts = [probe, *(p.relative_to(REPO_ROOT).as_posix() for p in _SCRIPTS)]
    excluded = [(g, s) for g in globs for s in scripts if _glob_matches(g, s)]
    assert excluded == [], "the plugin's .py scripts stay under ruff (D32)"


def test_g21_markdown_links_of_the_plugin_layer_are_self_contained(tmp_path: Path) -> None:
    source = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[PLUGIN_NAME])
    errors = check_markdown_links(source, tmp_path, LinksConfig())
    assert errors == [], "\n".join(f"{e.path}: {e.message}" for e in errors)


def _attribution_sections() -> tuple[list[str], dict[str, str]]:
    """``ATTRIBUTIONS.md``'s ``##`` headings, and each per-skill ``###`` section's text."""
    text = (PLUGIN_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    level_two = re.findall(r"^## (.+)$", text, flags=re.MULTILINE)
    per_skill = text.split(f"\n## {PER_SKILL_HEADING}\n", 1)[-1]
    chunks = re.split(r"^### (.+)$", per_skill, flags=re.MULTILINE)[1:]
    return level_two, dict(zip(chunks[::2], chunks[1::2], strict=True))


def test_g22_attributions_has_the_global_and_per_skill_sections_in_order() -> None:
    level_two, sections = _attribution_sections()
    assert level_two == [*ATTRIBUTIONS_GLOBAL_SECTIONS, PER_SKILL_HEADING]
    assert list(sections) == sorted(FINAL_IDS)


@pytest.mark.parametrize("skill_id", sorted(FINAL_IDS))
def test_g22_placeholder_only_in_the_sections_of_absent_skills(skill_id: str) -> None:
    section = _attribution_sections()[1][skill_id]
    if skill_id in _SKILLS:
        assert "_Filled by " not in section, f"### {skill_id} still holds its placeholder"
    else:
        assert placeholder(skill_id) in section, f"### {skill_id} lost {placeholder(skill_id)!r}"
