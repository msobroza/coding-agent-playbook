"""Self-tests of the ``mattpocock_skills`` gate scanners, on planted inputs.

The gates in ``test_gates.py`` pass on the vendored content; these tests show
each scanner fires on the forms specs/prT-mattpocock-skills.md sections 7.1 and
7.3 say it covers, so a scanner that silently matches nothing fails here.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import pytest

from tests.plugins.mattpocock_skills import _expectations
from tests.plugins.mattpocock_skills._expectations import _command_word, _is_denied_command
from tests.plugins.mattpocock_skills.test_gates import _claude_only_hits, _glob_matches

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_PROBE_SCRIPT = "catalog/plugins/mattpocock_skills/skills/wizard/scripts/wizard_template.py"


def _call(source: str) -> ast.Call:
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.Expr) and isinstance(node.value, ast.Call), source
    return node.value


@pytest.mark.parametrize(
    ("source", "word"),
    [
        ("subprocess.run(['open', 'u'])", "open"),
        ("subprocess.Popen(args=('xdg-open', 'u'))", "xdg-open"),
        ("subprocess.run('open u', shell=True)", "open"),
        ("os.system('start u')", "start"),
        ("os.execlp('open', 'open', 'u')", "open"),
        ("os.execvp('bash', ['bash', '-c', 'x'])", "bash"),
        ("os.execv('/usr/bin/open', ['open', 'u'])", "/usr/bin/open"),
    ],
)
def test_command_word_reads_every_covered_call_form(source: str, word: str) -> None:
    assert _command_word(_call(source)) == word
    assert _is_denied_command(word)


@pytest.mark.parametrize(
    "source", ["subprocess.run('open u')", "webbrowser.open('u')", "os.execv(program, args)"]
)
def test_command_word_ignores_non_literal_and_non_shell_forms(source: str) -> None:
    assert _command_word(_call(source)) is None


@pytest.mark.parametrize(
    "pattern",
    [
        "catalog/plugins/*",
        "**/scripts",
        "catalog/plugins/mattpocock_skills/skills/*/scripts",
        "catalog/*.py",
        "scripts",
        "catalog/plugins",
    ],
)
def test_glob_matches_a_glob_that_prunes_an_ancestor_directory(pattern: str) -> None:
    # Ruff prunes a directory whose path or name matches, and its ``*`` crosses ``/``.
    assert _glob_matches(pattern, _PROBE_SCRIPT)


@pytest.mark.parametrize(
    "pattern",
    [
        "catalog/plugins/mattpocock_skills/**/*.md",
        "catalog/plugins/superpowers",
        "catalog/plugins/*/eval_tasks/*/setup",
        "plugins/mattpocock_skills",
    ],
)
def test_glob_matches_leaves_the_scripts_under_the_repo_excludes(pattern: str) -> None:
    assert not _glob_matches(pattern, _PROBE_SCRIPT)


def test_g7_scans_the_scripts_of_a_skill(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "mattpocock_skills"
    scripts = root / "skills" / "probe" / "scripts"
    scripts.mkdir(parents=True)
    (root / "skills" / "probe" / "SKILL.md").write_text("---\nid: probe\n---\n", encoding="utf-8")
    (scripts / "x.py").write_text("# then call AskUserQuestion\n", encoding="utf-8")
    monkeypatch.setattr(_expectations, "PLUGIN_ROOT", root)
    monkeypatch.setattr(_expectations, "SKILLS_ROOT", root / "skills")
    monkeypatch.setattr(_expectations, "RULES_ROOT", root / "rules")
    assert [hit.path for hit in _claude_only_hits("probe")] == ["scripts/x.py"]
