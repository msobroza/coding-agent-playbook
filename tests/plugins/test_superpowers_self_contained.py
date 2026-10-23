"""Self-containment gate for the bundled ``superpowers`` plugin (SPEC §11.5).

The plugin must work with nothing installed beyond the engine: no URLs of any
scheme, no ``superpowers:<skill>`` plugin-namespace references (the upstream
plugin is never installed), no upstream-plugin markers, ``references/`` and
``scripts/`` path mentions that resolve inside the plugin, and scripts that stay
executable and parse. The URL and namespace scans cover every file in the
plugin (``skills/`` plus ``README.md``, ``LICENSE`` and ``ATTRIBUTIONS.md``),
not just markdown.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from tests.plugins.superpowers_expectations import (
    EXPECTED_SCRIPT_SUPPORT_FILES,
    EXPECTED_SCRIPTS,
    EXPECTED_SKILL_IDS,
    PLUGIN_ROOT,
    SKILLS_ROOT,
    UNRESOLVED_PATH_MENTIONS,
    pack_files,
    resource_files,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

# Any `scheme://`, `mailto:` or bare `www.` form: the policy is "no URL", not "no http".
_URL_RE = re.compile(rb"(?i)(?:\b[a-z][a-z0-9+.-]*://|\bmailto:|\bwww\.)")
_NAMESPACE_RE = re.compile(rb"superpowers:[A-Za-z]")
# Text that only works with the upstream plugin installed or its repo at hand.
# Scanned over skills/ only: ATTRIBUTIONS.md names the upstream repository.
_PLUGIN_COUPLING_RE = re.compile(
    rb"CLAUDE_PLUGIN_ROOT|obra/superpowers|gh issue|plugins/superpowers"
)
# A `references/...` or `scripts/...` path named in prose, inline code, a link or a
# graph label, optionally `../<skill>/`-prefixed. Paths are skill-dir relative, as
# upstream wrote them; the lookbehind skips the tail of a longer path.
_PATH_MENTION_RE = re.compile(
    r"(?<![\w./-])(?:\./)?(?:\.\./(?P<skill>[a-z0-9-]+)/)?"
    r"(?P<path>(?:references|scripts)/[\w./-]*[\w-])"
)
# Upstream's skill-root `prompts/`, `templates/` and `examples/` dirs now live under
# `references/`; a bare mention of one is a path the port forgot to move.
_PRE_MOVE_DIR_RE = re.compile(r"(?<![\w./-])(?:\./)?(?:prompts|templates|examples)/[\w.-]")
# `../<skill>/scripts/<file>` in a SKILL.md — a sibling-skill helper the reader
# runs; valid only because sync writes every pack skill as a sibling directory.
_SIBLING_SCRIPT_RE = re.compile(r"\.\./([a-z0-9-]+)/scripts/([\w.-]+)")
# `$(dirname "$0")/../../<skill>/scripts` inside a script: the same contract.
_SCRIPT_SIBLING_DIR_RE = re.compile(r"\.\./\.\./([a-z0-9-]+)/scripts")
# executing-plans' helpers call subagent-driven-development's via `$sdd/<name>`.
_SDD_HELPER_RE = re.compile(r"\$sdd/([\w.-]+)")
# Every shipped script is bash except writing-skills' Node renderer.
_SHELL_SCRIPTS = sorted(
    script for script in EXPECTED_SCRIPTS if not script.endswith((".js", ".mjs"))
)


def _offending_lines(pattern: re.Pattern[bytes], files: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in files:
        for lineno, line in enumerate(path.read_bytes().splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(PLUGIN_ROOT)}:{lineno}")
    return hits


def _markdown_docs() -> list[Path]:
    """Every SKILL.md plus every markdown file under a skill's references/."""
    return sorted(SKILLS_ROOT.glob("*/SKILL.md")) + sorted(SKILLS_ROOT.glob("*/references/**/*.md"))


def _unresolved_path_mentions() -> set[tuple[str, str]]:
    unresolved: set[tuple[str, str]] = set()
    for doc in _markdown_docs():
        skill_id = doc.relative_to(SKILLS_ROOT).parts[0]
        for match in _PATH_MENTION_RE.finditer(doc.read_text(encoding="utf-8")):
            target_skill = match.group("skill") or skill_id
            if (SKILLS_ROOT / target_skill / match.group("path")).exists():
                continue
            mention = match.group("path")
            if match.group("skill"):
                mention = f"../{target_skill}/{mention}"
            unresolved.add((doc.relative_to(SKILLS_ROOT).as_posix(), mention))
    return unresolved


def _script_paths() -> list[Path]:
    return sorted(path for path in SKILLS_ROOT.glob("*/scripts/**/*") if path.is_file())


def _is_shell_script(path: Path) -> bool:
    first_line = path.read_text(encoding="utf-8").split("\n", 1)[0]
    return first_line.startswith("#!") and ("bash" in first_line or first_line.endswith("sh"))


def test_scans_cover_the_whole_plugin() -> None:
    scanned = {path.relative_to(PLUGIN_ROOT).as_posix() for path in pack_files()}
    # The plugin-root files ship in the wheel but are never synced; scanning them
    # keeps the README's enable instructions URL- and namespace-free too.
    root_files = {"LICENSE", "ATTRIBUTIONS.md", "README.md", "framework.toml"}
    assert {rel for rel in scanned if "/" not in rel} == root_files
    assert set(resource_files()) <= set(pack_files())


def test_no_urls_anywhere_in_pack() -> None:
    hits = _offending_lines(_URL_RE, pack_files())
    assert not hits, f"URLs remain: {hits}"


def test_no_plugin_namespace_skill_refs() -> None:
    hits = _offending_lines(_NAMESPACE_RE, pack_files())
    assert not hits, f"'superpowers:<skill>' refs remain: {hits}"


def test_no_upstream_plugin_coupling_markers() -> None:
    hits = _offending_lines(_PLUGIN_COUPLING_RE, resource_files())
    assert not hits, f"upstream-plugin coupling remains: {hits}"


def test_path_mentions_resolve_inside_the_pack() -> None:
    # Regression guard for the port's restructure: a moved file whose inline
    # mention (e.g. `references/templates/report.md`) was not updated, or a
    # reference file dropped from the pack, must fail here. The allowlist is
    # compared both ways so a stale entry fails too.
    assert _unresolved_path_mentions() == set(UNRESOLVED_PATH_MENTIONS)


def test_no_mentions_of_pre_move_directories() -> None:
    hits = [
        f"{doc.relative_to(SKILLS_ROOT)}:{lineno}"
        for doc in _markdown_docs()
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1)
        if _PRE_MOVE_DIR_RE.search(line)
    ]
    assert not hits, f"mentions of upstream's pre-move dirs (now under references/): {hits}"


@pytest.mark.parametrize("skill_id", sorted(EXPECTED_SKILL_IDS))
def test_sibling_script_mentions_resolve(skill_id: str) -> None:
    body = (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")
    missing = [
        match.group(0)
        for match in _SIBLING_SCRIPT_RE.finditer(body)
        if not (SKILLS_ROOT / match.group(1) / "scripts" / match.group(2)).is_file()
    ]
    assert not missing, f"{skill_id}/SKILL.md names missing sibling scripts: {missing}"


def test_pack_ships_exactly_the_expected_scripts() -> None:
    shipped = {path.relative_to(SKILLS_ROOT).as_posix() for path in _script_paths()}
    assert shipped == EXPECTED_SCRIPTS | EXPECTED_SCRIPT_SUPPORT_FILES


def test_node_renderer_declares_its_module_type() -> None:
    # Regression: without this sidecar, `node scripts/render-graphs.js` died with
    # "Cannot use import statement outside a module" once vendored (the upstream
    # repo-root package.json that made it ESM is not in the pack).
    sidecar = SKILLS_ROOT / "writing-skills" / "scripts" / "package.json"
    assert json.loads(sidecar.read_text(encoding="utf-8")) == {"type": "module"}


@pytest.mark.parametrize("script", sorted(EXPECTED_SCRIPTS))
def test_script_is_executable(script: str) -> None:
    assert os.access(SKILLS_ROOT / script, os.X_OK), f"{script} lost its executable bit"


@pytest.mark.parametrize("script", sorted(EXPECTED_SCRIPTS))
def test_script_sibling_dirs_exist(script: str) -> None:
    text = (SKILLS_ROOT / script).read_text(encoding="utf-8")
    for match in _SCRIPT_SIBLING_DIR_RE.finditer(text):
        assert (SKILLS_ROOT / match.group(1) / "scripts").is_dir(), match.group(0)


def test_executing_plans_helpers_exist_in_sibling_skill() -> None:
    sdd_scripts = SKILLS_ROOT / "subagent-driven-development" / "scripts"
    for name in ("task-start", "task-done"):
        text = (SKILLS_ROOT / "executing-plans" / "scripts" / name).read_text(encoding="utf-8")
        helpers = _SDD_HELPER_RE.findall(text)
        assert helpers, f"{name} no longer calls a subagent-driven-development helper"
        missing = [helper for helper in helpers if not (sdd_scripts / helper).is_file()]
        assert not missing, f"{name} calls missing helpers {missing}"


@pytest.mark.parametrize("script", _SHELL_SCRIPTS)
def test_shell_script_parses(script: str) -> None:
    path = SKILLS_ROOT / script
    assert _is_shell_script(path), f"{script} lost its bash shebang"
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not on PATH")
    result = subprocess.run(
        [bash, "-n", str(path)], capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
