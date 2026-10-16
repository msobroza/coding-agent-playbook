"""Structure, self-containment and opt-in sync tests for the ``python_design`` pack.

SPEC §11.5.2. The pack is distilled (written fresh), not vendored, so apart from
the fixed contracts (the two skill ids and the three scripts) its files are
discovered rather than pinned. The checks: the pack is a bundled pack that stays
off by default; each ``SKILL.md`` has ``id == name ==`` its directory, a bounded
description, no Jinja and no markdown links (Continue keeps only that body);
every ``references/…`` / ``scripts/…`` path the docs name resolves inside the
same skill; every script is an executable, stdlib-only, Python 3.10 program that
passes ``mypy --strict``; and ``playbook init --overlays …`` then sync lands each
skill byte-identically in every native skill root of the enabled adapters.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.commands._sync_preflight import bundled_packs, unusable_overlays
from coding_agent_playbook.links import LinksConfig, extract_markdown_links
from coding_agent_playbook.packs.python_design import PACK_NAME
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource, _resource_subdir
from coding_agent_playbook.types import split_frontmatter
from tests._content import plugin_root
from tests.conftest import apply_hermetic_git_env
from tests.fakes import FakeGitClient
from tests.packs.superpowers_expectations import NATIVE_SKILL_ROOTS, SYNCED_SKILL_ENTRIES

PACK_ROOT = plugin_root("python_design")
SKILLS_ROOT = PACK_ROOT / "skills"
EXPECTED_SKILL_IDS = frozenset({"python-design-review", "python-architecture"})
#: The fixed script contracts, as ``<skill-id>/scripts/<file>``.
EXPECTED_SCRIPTS = frozenset(
    {
        "python-design-review/scripts/detect_smells.py",
        "python-design-review/scripts/lcom4_clusters.py",
        "python-architecture/scripts/layer_map.py",
    }
)
SHEBANG = "#!/usr/bin/env python3"
_SKILL_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_JINJA_RE = re.compile(r"\{\{|\{%|\{#")
#: A ``references/…`` or ``scripts/…`` path named in prose or code; the
#: lookbehind skips the tail of a longer path such as ``app/scripts/x.py``.
_PATH_MENTION_RE = re.compile(r"(?<![\w./-])(?:\./)?(?P<path>(?:references|scripts)/[\w./-]*[\w-])")
#: A ``../<dir>/`` hop: a skill reaching into a sibling skill is a dependency.
_SIBLING_HOP_RE = re.compile(r"\.\./[\w-]+/")
#: What the ``SkillWriter`` adds between the frontmatter and the source body.
_SENTINEL_BODY_PREFIX = f"<!-- {SENTINEL} -->\n\n"


def _relative_files(root: Path) -> list[str]:
    """Every file under ``root`` (POSIX, sorted), bytecode caches included."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _is_bytecode_cache(rel: str) -> bool:
    return "__pycache__" in rel.split("/") or rel.endswith((".pyc", ".pyo"))


def _source_files(root: Path) -> list[str]:
    """Files under a pack source ``root``, minus the bytecode caches that ``pip install``
    or an in-process script import leaves there (sync never copies them)."""
    return [rel for rel in _relative_files(root) if not _is_bytecode_cache(rel)]


def _in_subdir(rel: str, subdir: str, suffix: str) -> bool:
    """True for a ``<skill-id>/<subdir>/**/*<suffix>`` path relative to ``SKILLS_ROOT``."""
    parts = rel.split("/")
    return len(parts) > 2 and parts[1] == subdir and rel.endswith(suffix)


# Discovered at collection time: the content is distilled, so only the fixed
# contracts are pinned (a missing expected script still fails its tests). An
# empty tree fails collection rather than silently skipping every doc test.
_SKILL_FILES = _source_files(SKILLS_ROOT)
assert _SKILL_FILES, f"no skills under {SKILLS_ROOT}"
_DOCS = [
    rel
    for rel in _SKILL_FILES
    if rel.split("/")[1:] == ["SKILL.md"] or _in_subdir(rel, "references", ".md")
]
_SCRIPTS = sorted(EXPECTED_SCRIPTS | {r for r in _SKILL_FILES if _in_subdir(r, "scripts", ".py")})


def _split(skill_id: str) -> tuple[dict[str, object], str]:
    return split_frontmatter((SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8"))


# --- identity and opt-in ------------------------------------------------------


def test_pack_is_a_usable_bundled_pack() -> None:
    assert PACK_NAME == "coding_agent_playbook.packs.python_design"
    assert PACK_NAME in bundled_packs()
    assert unusable_overlays([PACK_NAME]) == []


def test_pack_ships_only_the_two_skills() -> None:
    assert sorted(p.name for p in PACK_ROOT.iterdir() if p.is_dir()) == ["skills"]
    assert {p.name for p in SKILLS_ROOT.iterdir() if p.is_dir()} == EXPECTED_SKILL_IDS


def test_pack_is_off_by_default_and_adds_only_skills(tmp_path: Path) -> None:
    plain = FileSystemArtifactSource(repo_root=tmp_path)
    with_pack = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[PACK_NAME])
    assert not [s for s in plain.list_skills() if s.source_package == PACK_NAME]
    pack_ids = {s.frontmatter.get("id") for s in with_pack.list_skills()} - {
        s.frontmatter.get("id") for s in plain.list_skills()
    }
    assert pack_ids == EXPECTED_SKILL_IDS
    assert len(with_pack.list_rules()) == len(plain.list_rules())
    assert len(with_pack.list_prompts()) == len(plain.list_prompts())


# --- SKILL.md and references --------------------------------------------------


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_skill_dir_holds_only_synced_entries(skill_id: str) -> None:
    entries = {p.name for p in (SKILLS_ROOT / skill_id).iterdir() if p.name != "__pycache__"}
    assert "SKILL.md" in entries
    assert entries <= SYNCED_SKILL_ENTRIES, (
        f"sync would drop {sorted(entries - SYNCED_SKILL_ENTRIES)}"
    )


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_skill_frontmatter_identity_and_description(skill_id: str) -> None:
    frontmatter, _ = _split(skill_id)
    assert frontmatter.get("id") == frontmatter.get("name") == skill_id
    assert _SKILL_ID_RE.match(skill_id) and len(skill_id) <= 64
    description = frontmatter.get("description")
    assert isinstance(description, str) and 1 <= len(description) <= 1024
    assert not re.match(r"(?i)(i|you|we)\b", description), "write the description in third person"


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_skill_md_is_plain_markdown_without_jinja(skill_id: str) -> None:
    assert not list((SKILLS_ROOT / skill_id).rglob("*.j2"))
    text = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
    assert not _JINJA_RE.search(text), "SKILL.md is plain markdown, never a template"


@pytest.mark.parametrize("doc", _DOCS)
def test_doc_has_no_markdown_links(doc: str) -> None:
    # Continue keeps only the SKILL.md body and AGENTS.md drops skills, so a
    # link could dangle; files are named in plain text instead.
    links = extract_markdown_links((SKILLS_ROOT / doc).read_text(encoding="utf-8"))
    assert links == [], [f"line {link.line}: {link.target}" for link in links]


@pytest.mark.parametrize("doc", _DOCS)
def test_doc_path_mentions_resolve_inside_its_own_skill(doc: str) -> None:
    text = (SKILLS_ROOT / doc).read_text(encoding="utf-8")
    skill_dir = SKILLS_ROOT / Path(doc).parts[0]
    mentions = {m.group("path") for m in _PATH_MENTION_RE.finditer(text)}
    assert sorted(p for p in mentions if not (skill_dir / p).exists()) == []
    assert _SIBLING_HOP_RE.findall(text) == [], "a skill must not reach into another skill"


# --- scripts -------------------------------------------------------------------


@pytest.mark.parametrize("script", _SCRIPTS)
def test_script_is_an_executable_python3_program(script: str) -> None:
    path = SKILLS_ROOT / script
    assert path.read_text(encoding="utf-8").split("\n", 1)[0] == SHEBANG
    if os.name != "nt":  # Windows has no executable bit to check
        assert os.access(path, os.X_OK), f"{script} is not executable (chmod +x)"


@pytest.mark.parametrize("script", _SCRIPTS)
def test_script_parses_as_310_and_imports_only_stdlib(script: str) -> None:
    path = SKILLS_ROOT / script
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=script, feature_version=(3, 10))
    docstring = ast.get_docstring(tree) or ""
    assert path.name in docstring, "the module docstring must carry a usage line"
    assert _non_stdlib_imports(tree) == []


def _non_stdlib_imports(tree: ast.Module) -> list[str]:
    """Imported top-level names outside the stdlib; a relative import counts too."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append("." * node.level + (node.module or ""))
    return sorted(n for n in names if n.split(".")[0] not in sys.stdlib_module_names)


@pytest.fixture(scope="module")
def mypy_workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A neutral cwd + empty config + shared cache, so the repo config never applies."""
    workdir = tmp_path_factory.mktemp("mypy-scripts")
    (workdir / "mypy.ini").write_text("[mypy]\n", encoding="utf-8")
    return workdir


@pytest.mark.parametrize("script", _SCRIPTS)
def test_script_passes_strict_mypy_for_python_310(script: str, mypy_workdir: Path) -> None:
    command = [sys.executable, "-m", "mypy", "--strict", "--python-version", "3.10"]
    command += ["--config-file", str(mypy_workdir / "mypy.ini")]
    command += ["--cache-dir", str(mypy_workdir / "cache"), str(SKILLS_ROOT / script)]
    proc = subprocess.run(
        command, cwd=mypy_workdir, capture_output=True, text=True, timeout=300, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# --- opt-in sync through `playbook init --overlays …` ---------------------------


def _init_probe(repo: Path, *, overlays: str | None, adapters: str | None = None) -> Path:
    """``playbook init --non-interactive`` (which ends with a sync) in ``repo``."""
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "probe"\nrequires-python = ">=3.10"\ndependencies = []\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(
        repo_root=str(repo),
        non_interactive=True,
        name="probe",
        kind="python-application",
        description="",
        adapters=adapters,
        overlays=overlays,
    )
    assert _init.run(args) == 0
    return repo


@pytest.fixture(scope="module")
def opted_in_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One probe consumer repo, opted in with the default adapters, shared read-only."""
    repo = tmp_path_factory.mktemp("python-design-consumer")
    with pytest.MonkeyPatch.context() as patch:
        config_home = tmp_path_factory.mktemp("xdg-config")
        apply_hermetic_git_env(patch, ceiling=repo.parent, config_home=config_home)
        return _init_probe(repo, overlays=PACK_NAME)


def test_init_writes_the_top_level_overlay_key(opted_in_repo: Path) -> None:
    config = tomllib.loads((opted_in_repo / ".coding-agent-playbook.toml").read_text("utf-8"))
    assert config["overlays_enabled"] == [PACK_NAME]


@pytest.mark.parametrize("root", NATIVE_SKILL_ROOTS)
@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_sync_writes_the_skill_md_with_its_source_body(
    opted_in_repo: Path, root: str, skill_id: str
) -> None:
    written = split_frontmatter((opted_in_repo / root / skill_id / "SKILL.md").read_text("utf-8"))
    source_frontmatter, source_body = _split(skill_id)
    assert written[0] == source_frontmatter
    assert written[1] == _SENTINEL_BODY_PREFIX + source_body


@pytest.mark.parametrize("root", NATIVE_SKILL_ROOTS)
@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_sync_copies_scripts_and_references_byte_for_byte(
    opted_in_repo: Path, root: str, skill_id: str
) -> None:
    for subdir in ("references", "scripts"):
        source, synced = SKILLS_ROOT / skill_id / subdir, opted_in_repo / root / skill_id / subdir
        assert source.is_dir(), f"{skill_id} ships no {subdir}/"
        # Unfiltered on the synced side: a bytecode cache leaking into a root fails here.
        assert _relative_files(synced) == _source_files(source), f"{root}/{skill_id}/{subdir}"
        for rel in _source_files(source):
            assert (synced / rel).read_bytes() == (source / rel).read_bytes(), rel
            if subdir == "scripts" and rel.endswith(".py") and os.name != "nt":
                assert os.access(synced / rel, os.X_OK), f"{root}/{skill_id}/scripts/{rel}"


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_continue_degrades_each_skill_to_its_skill_md_body(
    opted_in_repo: Path, skill_id: str
) -> None:
    text = (opted_in_repo / ".continue" / "prompts" / f"{skill_id}.md").read_text("utf-8")
    assert SENTINEL in text.split("\n", 1)[0]
    assert text.endswith(_split(skill_id)[1])


def test_validate_and_sync_check_pass_with_the_pack_enabled(
    opted_in_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _validate.run(argparse.Namespace(repo_root=str(opted_in_repo))) == 0
    assert _sync.execute(opted_in_repo, check=True, git=FakeGitClient()) == 0, (
        capsys.readouterr().out
    )


def test_link_gate_walks_and_passes_over_the_pack(tmp_path: Path) -> None:
    walked = _resource_subdir(PACK_NAME, "skills")
    assert walked is not None and walked.resolve() == SKILLS_ROOT.resolve()
    source = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[PACK_NAME])
    errors = _validate._check_markdown_links(source, tmp_path, LinksConfig())
    assert errors == [], "\n".join(f"{e.path}: {e.message}" for e in errors)


def test_synced_scripts_run_from_the_consumer_tree(opted_in_repo: Path, tmp_path: Path) -> None:
    source = "def add(item, basket=[]):\n    return basket\n"
    (tmp_path / "orders.py").write_text(source, encoding="utf-8")
    skills = opted_in_repo / ".claude" / "skills"
    smells = _run_json(skills / "python-design-review/scripts/detect_smells.py", tmp_path)
    assert [hit["smell"] for hit in smells] == ["mutable-default-argument"]
    assert _run_json(skills / "python-design-review/scripts/lcom4_clusters.py", tmp_path) == []
    layers = _run_json(skills / "python-architecture/scripts/layer_map.py", tmp_path, "--json")
    assert layers["violations"] == [] and layers["cycles"] == []


def _run_json(script: Path, target: Path, *extra: str) -> Any:  # parsed JSON: a list or an object
    """Run a synced script on ``target`` (exit 0 expected) and parse its JSON stdout."""
    proc = subprocess.run(
        [sys.executable, str(script), str(target), *extra],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.usefixtures("hermetic_git_env")
def test_init_without_the_overlay_writes_no_pack_skills(tmp_path: Path) -> None:
    repo = _init_probe(tmp_path, overlays=None)
    for root in (*NATIVE_SKILL_ROOTS, ".continue/prompts"):
        assert not [p for p in (repo / root).glob("python-*") if p.stem in EXPECTED_SKILL_IDS]


@pytest.mark.usefixtures("hermetic_git_env")
def test_skills_land_only_in_the_roots_of_enabled_adapters(tmp_path: Path) -> None:
    repo = _init_probe(tmp_path, overlays=PACK_NAME, adapters="claude_code")
    for skill_id in sorted(EXPECTED_SKILL_IDS):
        assert (repo / ".claude" / "skills" / skill_id / "SKILL.md").is_file()
        assert not (repo / ".opencode" / "skills" / skill_id).exists()
        assert not (repo / "shared_skills" / skill_id).exists()
