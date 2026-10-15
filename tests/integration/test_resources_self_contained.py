"""CI gate: every shipped resource is self-contained (no URLs, no plugin markers).

The engine's artifacts load straight into an agent's context, often in an
air-gapped deployment, so a rule, prompt or skill must never point outside the
shipped bundle and must never name the third-party source some of them were
distilled from. Credit for that source lives in exactly two places:
``resources/ATTRIBUTIONS.md`` for the engine's own artifacts and
``packs/python_design/ATTRIBUTIONS.md`` for the distilled ``python_design`` pack.
The PR-L link gate (``links.py``) cannot enforce this: it recognizes only
markdown link syntax, masks code spans, and reads only ``.md``/``.md.j2``. This
scan applies no masking and reads every text file.

Scope: every file under ``resources/`` and every file of the ``python_design``
pack (its ``resources/`` plus ``ATTRIBUTIONS.md`` and ``__init__.py``; ids are
prefixed ``packs/python_design/``), dot dirs and bytecode caches aside. The pack's
files are all fully scanned except its ``ATTRIBUTIONS.md``, which is URL-free but
must name the plugin (:func:`pack_policy_for`). For ``resources/`` the checks are
decided per file by :func:`policy_for`:

* by default -> URLs and plugin markers are both violations. That includes the
  eval fixtures under ``eval_tasks/<id>/setup/`` and ``solution/``: they ship in
  the wheel and are copied into the agent's scratch repo. No fixture needs a URL
  today; if one ever does, allow only a reserved example host (``example.com``,
  ``*.test``, ``*.invalid``, ``localhost``) for that one path;
* ``resources/ATTRIBUTIONS.md`` -> URL-free, but it *must* name the plugin, so
  the marker scan is off;
* ``eval_tasks/**/ATTRIBUTIONS.md`` outside fixture trees -> markers only: the
  CC BY 4.0 licence requires its licence URI (pinned by
  ``test_crosscommitvuln_fixtures.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

_ENGINE_ROOT = Path(__file__).resolve().parents[2] / "src" / "coding_agent_playbook"
_RESOURCES_ROOT = _ENGINE_ROOT / "resources"
#: The distilled opt-in pack (SPEC §11.5.2): all of it ships, so all of it is scanned.
_PYTHON_DESIGN_ROOT = _ENGINE_ROOT / "packs" / "python_design"
_PYTHON_DESIGN_PREFIX = "packs/python_design/"

_EVAL_TASKS_SUBDIR = "eval_tasks"
#: Per-task fixture trees: ``eval_tasks/<id>/setup/**`` and ``eval_tasks/<id>/solution/**``.
_FIXTURE_DIRS = frozenset({"setup", "solution"})
_ATTRIBUTIONS_NAME = "ATTRIBUTIONS.md"

#: Any ``scheme://``, ``www.``, an scp-style git remote, ``mailto:``, and a bare
#: domain followed by a path (``docs.python.org/3/``, ``//cdn.host.org/x.js``). The
#: bare form needs the ``/`` so attribute access (``self.io``, ``pkg.net``) and
#: module paths never match. ``\S*`` captures the rest so the failure shows the leak.
_URL_RE = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://\S*"
    r"|\bwww\.\S*"
    r"|\bgit@[\w.-]+:\S*"
    r"|\bmailto:\S+"
    r"|\b(?:[a-z0-9-]+\.)+(?:com|org|net|io|dev|ai|gov|edu|co)/\S*"
)
#: The distilled plugin's name (any spacing), its copyright holder, the author and
#: their course, and its install-path tokens: the ``${CLAUDE_PLUGIN_ROOT}/...``
#: footer is the likeliest copy-paste leak. ``\b`` keeps names like "Marjan" clean.
_PLUGIN_MARKER_RE = re.compile(
    r"(?i)python[\s_-]*clean[\s_-]*architecture|\barjan|\bmk[\s_-]*toronto"
    r"|software[\s_-]*designer[\s_-]*mindset|claude_plugin_root|\.claude/plugins"
)


@dataclass(frozen=True)
class ScanPolicy:
    """Which checks apply to one file."""

    urls: bool
    markers: bool


@dataclass(frozen=True)
class ScanTarget:
    """One file to scan, its path relative to the resources root, and its policy."""

    path: Path
    rel: str
    policy: ScanPolicy


@dataclass(frozen=True)
class Violation:
    """One offending match: where it is, which check flagged it, and the text."""

    rel: str
    line: int
    kind: str
    text: str

    def render(self) -> str:
        return f"{self.rel}:{self.line}: {self.kind}: {self.text!r}"


def policy_for(rel: Path) -> ScanPolicy:
    """Return the checks for ``rel`` (a path relative to ``resources/``).

    >>> policy_for(Path("ATTRIBUTIONS.md"))
    ScanPolicy(urls=True, markers=False)
    """
    if rel == Path(_ATTRIBUTIONS_NAME):
        # The one sanctioned home of the credit: it names the plugin by design.
        return ScanPolicy(urls=True, markers=False)
    if (
        rel.name == _ATTRIBUTIONS_NAME
        and rel.parts[0] == _EVAL_TASKS_SUBDIR
        and not _is_fixture(rel)
    ):
        # CC BY 4.0 requires the licence URI next to the derived fixtures.
        return ScanPolicy(urls=False, markers=True)
    return ScanPolicy(urls=True, markers=True)


def pack_policy_for(rel: Path) -> ScanPolicy:
    """Return the checks for ``rel`` (a path relative to the ``python_design`` pack root).

    The pack's own ``ATTRIBUTIONS.md`` is its one sanctioned home of the credit;
    every other pack file (skills, scripts, ``__init__.py``) gets both checks.

    >>> pack_policy_for(Path("ATTRIBUTIONS.md"))
    ScanPolicy(urls=True, markers=False)
    """
    return ScanPolicy(urls=True, markers=rel != Path(_ATTRIBUTIONS_NAME))


def _is_fixture(rel: Path) -> bool:
    """True for ``eval_tasks/<id>/setup/**`` and ``eval_tasks/<id>/solution/**``."""
    parts = rel.parts
    return len(parts) > 3 and parts[0] == _EVAL_TASKS_SUBDIR and parts[2] in _FIXTURE_DIRS


def _is_hidden(path: Path, root: Path) -> bool:
    # Dot entries (e.g. a local .pytest_cache inside a fixture) and bytecode
    # caches are tool output, never shipped artifacts.
    parts = path.relative_to(root).parts
    return any(p.startswith(".") or p == "__pycache__" for p in parts)


def scan_targets(
    root: Path, *, prefix: str = "", policy: Callable[[Path], ScanPolicy] = policy_for
) -> list[ScanTarget]:
    """Every file the gate scans under ``root``, sorted by relative path.

    Each id is ``prefix`` + the path relative to ``root``; ``policy`` sees the
    unprefixed relative path. An empty or missing ``root`` fails loudly: a gate
    that scans nothing passes vacuously. Example::

        scan_targets(pack_root, prefix="packs/python_design/", policy=pack_policy_for)
    """
    # POSIX-style ids keep the test ids and prefix checks stable on Windows too.
    rels = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not _is_hidden(p, root)
    )
    assert rels, f"nothing scanned under {root}"
    return [ScanTarget(root / rel, prefix + rel, policy(Path(rel))) for rel in rels]


def scan_text(text: str, rel: str, policy: ScanPolicy) -> list[Violation]:
    """Return every URL / plugin-marker hit in ``text`` that ``policy`` forbids.

    >>> scan_text("see www.example.org", "r.md", ScanPolicy(urls=True, markers=True))
    [Violation(rel='r.md', line=1, kind='url', text='www.example.org')]
    """
    checks = [("url", _URL_RE, policy.urls), ("plugin-marker", _PLUGIN_MARKER_RE, policy.markers)]
    found: list[Violation] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pattern, enabled in checks:
            if enabled:
                found += [Violation(rel, lineno, kind, m.group(0)) for m in pattern.finditer(line)]
    return found


def scan_file(target: ScanTarget) -> list[Violation]:
    """Scan one file; a non-UTF-8 (binary) file has no text to leak and passes."""
    try:
        text = target.path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    return scan_text(text, target.rel, target.policy)


_TARGETS = scan_targets(_RESOURCES_ROOT) + scan_targets(
    _PYTHON_DESIGN_ROOT, prefix=_PYTHON_DESIGN_PREFIX, policy=pack_policy_for
)


@pytest.mark.parametrize("target", _TARGETS, ids=lambda t: t.rel)
def test_shipped_resource_is_self_contained(target: ScanTarget) -> None:
    violations = scan_file(target)
    assert violations == [], (
        "shipped resources must carry no URLs and must not name the plugin they were "
        "distilled from (credit lives only in resources/ATTRIBUTIONS.md and "
        f"{_PYTHON_DESIGN_PREFIX}{_ATTRIBUTIONS_NAME}):\n"
        + "\n".join(v.render() for v in violations)
    )


def test_scan_covers_every_artifact_kind() -> None:
    """Guard against a walker that silently scans nothing."""
    rels = {t.rel for t in _TARGETS}
    for prefix in ("rules/", "prompts/", "precommit/", f"{_PYTHON_DESIGN_PREFIX}resources/skills/"):
        assert any(r.startswith(prefix) for r in rels), f"nothing scanned under {prefix}"
    for part in ("/task.toml", "/setup/", "/solution/"):
        assert any(part in r for r in rels), f"no eval-task file matching {part} scanned"
    assert _ATTRIBUTIONS_NAME in rels
    assert f"{_EVAL_TASKS_SUBDIR}/{_ATTRIBUTIONS_NAME}" in rels
    assert f"{_PYTHON_DESIGN_PREFIX}{_ATTRIBUTIONS_NAME}" in rels
    assert f"{_PYTHON_DESIGN_PREFIX}__init__.py" in rels


def test_pack_scan_exempts_only_the_pack_attributions_from_the_marker_check() -> None:
    exempt = {t.rel for t in _TARGETS if t.rel.startswith(_PYTHON_DESIGN_PREFIX)} - {
        t.rel for t in _TARGETS if t.policy == ScanPolicy(urls=True, markers=True)
    }
    assert exempt == {f"{_PYTHON_DESIGN_PREFIX}{_ATTRIBUTIONS_NAME}"}


@pytest.mark.parametrize(
    "attributions",
    [_RESOURCES_ROOT / _ATTRIBUTIONS_NAME, _PYTHON_DESIGN_ROOT / _ATTRIBUTIONS_NAME],
    ids=["resources", "python_design"],
)
def test_attributions_credit_the_distilled_source(attributions: Path) -> None:
    text = attributions.read_text(encoding="utf-8")
    assert "python-clean-architecture" in text
    assert "MKToronto" in text
    assert "MIT" in text


# --------------------------------------------------------------------------- #
# The scanner itself, on synthetic input (independent of shipped content).
# --------------------------------------------------------------------------- #

_BOTH = ScanPolicy(urls=True, markers=True)


@pytest.mark.parametrize(
    ("line", "kind", "text"),
    [
        ("See https://example.org/x for more.", "url", "https://example.org/x"),
        ("plain HTTP://Example.org works too", "url", "HTTP://Example.org"),
        ("visit www.example.org today", "url", "www.example.org"),
        ("in `http://localhost:8000` code spans", "url", "http://localhost:8000`"),
        ("fetch ftp://files.example.org/x", "url", "ftp://files.example.org/x"),
        ("ssh://git@host/repo", "url", "ssh://git@host/repo"),
        ("read file:///etc/passwd", "url", "file:///etc/passwd"),
        ("clone git@github.com:owner/repo.git", "url", "git@github.com:owner/repo.git"),
        ("write to mailto:someone@example.org", "url", "mailto:someone@example.org"),
        ("docs at docs.python.org/3/library", "url", "docs.python.org/3/library"),
        ("load //cdn.example.org/x.js", "url", "cdn.example.org/x.js"),
        ("Distilled from Python-Clean-Architecture.", "plugin-marker", "Python-Clean-Architecture"),
        (
            "Review against Python Clean Architecture rules",
            "plugin-marker",
            "Python Clean Architecture",
        ),
        ("import python_clean_architecture", "plugin-marker", "python_clean_architecture"),
        ("as taught by ARJAN codes", "plugin-marker", "ARJAN"),
        ("(c) MKToronto", "plugin-marker", "MKToronto"),
        ("Copyright MK Toronto", "plugin-marker", "MK Toronto"),
        ("from the Software Designer Mindset course", "plugin-marker", "Software Designer Mindset"),
        ("Load `${CLAUDE_PLUGIN_ROOT}/skills/x.md`.", "plugin-marker", "CLAUDE_PLUGIN_ROOT"),
        ("Copied from ~/.claude/plugins/cache/foo.", "plugin-marker", ".claude/plugins"),
    ],
)
def test_scan_text_flags_leaks(line: str, kind: str, text: str) -> None:
    assert scan_text(f"ok\n{line}\n", "x.md", _BOTH) == [Violation("x.md", 2, kind, text)]


def test_scan_text_passes_clean_text() -> None:
    """Ordinary prose and Python code never trip either check."""
    clean = (
        "Inject dependencies through the constructor.\nUse httpx timeouts.\n"
        "Marjan and Farjana wrote the tests.\n"
        "Edit pyproject.toml; from shop.orders import place_order\n"
        "asyncio.run(main()) reads settings.api_url\n"
        "self.io, pkg.net and user.org stay attributes; half = total // 2\n"
    )
    assert scan_text(clean, "x.md", _BOTH) == []


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("rules/languages/python/pure-core.md", ScanPolicy(urls=True, markers=True)),
        ("prompts/characterize.md", ScanPolicy(urls=True, markers=True)),
        ("precommit/config.yaml.j2", ScanPolicy(urls=True, markers=True)),
        ("eval_tasks/some-task/task.toml", ScanPolicy(urls=True, markers=True)),
        ("eval_tasks/some-task/setup/app/db.py", ScanPolicy(urls=True, markers=True)),
        ("eval_tasks/some-task/solution/transcript.md", ScanPolicy(urls=True, markers=True)),
        ("ATTRIBUTIONS.md", ScanPolicy(urls=True, markers=False)),
        ("eval_tasks/ATTRIBUTIONS.md", ScanPolicy(urls=False, markers=True)),
        ("eval_tasks/some-task/ATTRIBUTIONS.md", ScanPolicy(urls=False, markers=True)),
        ("eval_tasks/some-task/setup/ATTRIBUTIONS.md", ScanPolicy(urls=True, markers=True)),
        ("rules/ATTRIBUTIONS.md", ScanPolicy(urls=True, markers=True)),
    ],
)
def test_policy_for(rel: str, expected: ScanPolicy) -> None:
    assert policy_for(Path(rel)) == expected


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("ATTRIBUTIONS.md", ScanPolicy(urls=True, markers=False)),
        ("__init__.py", ScanPolicy(urls=True, markers=True)),
        ("resources/skills/s/SKILL.md", ScanPolicy(urls=True, markers=True)),
        ("resources/skills/s/scripts/run.py", ScanPolicy(urls=True, markers=True)),
        ("resources/skills/s/references/ATTRIBUTIONS.md", ScanPolicy(urls=True, markers=True)),
    ],
)
def test_pack_policy_for(rel: str, expected: ScanPolicy) -> None:
    assert pack_policy_for(Path(rel)) == expected


def test_pack_scan_targets_on_a_synthetic_tree(tmp_path: Path) -> None:
    """Pack ids carry the prefix; only the pack-root ATTRIBUTIONS.md may name the plugin."""
    files = {
        "ATTRIBUTIONS.md": "Credit: python-clean-architecture (MIT).\n",
        "__init__.py": '"""See www.example.org."""\n',
        "resources/skills/s/SKILL.md": "As Arjan teaches.\n",
        "resources/skills/s/__pycache__/x.pyc": "https://example.org\n",
    }
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")

    targets = scan_targets(tmp_path, prefix="packs/p/", policy=pack_policy_for)
    violations = [v.render() for t in targets for v in scan_file(t)]

    assert violations == [
        'packs/p/__init__.py:1: url: \'www.example.org."""\'',
        "packs/p/resources/skills/s/SKILL.md:1: plugin-marker: 'Arjan'",
    ]


def test_scan_targets_on_a_synthetic_tree(tmp_path: Path) -> None:
    """Every file is scanned, fixtures included; only attribution notes are exempt."""
    files = {
        "ATTRIBUTIONS.md": "Credit: python-clean-architecture.\n",
        "rules/a.md": "Read https://example.org first.\n",
        "prompts/p.md.j2": "clean\n",
        "precommit/config.yaml.j2": "repo: https://example.org/hooks\n",
        "skills/s/scripts/run.py": "# mktoronto\n",
        "eval_tasks/ATTRIBUTIONS.md": "Licence: https://licence.example\n",
        "eval_tasks/t/task.toml": 'description = "see www.example.org"\n',
        "eval_tasks/t/setup/app.py": 'URL = "https://api.example.org"\n',
        "eval_tasks/t/setup/ATTRIBUTIONS.md": "https://example.org\n",
        "eval_tasks/t/solution/transcript.md": "Adapted from Arjan's example.\n",
        "eval_tasks/t/solution/negatives/wrong.md": "clean\n",
        "rules/.cache/junk.md": "https://example.org\n",
    }
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")

    violations = [v.render() for t in scan_targets(tmp_path) for v in scan_file(t)]

    assert violations == [
        "eval_tasks/t/setup/ATTRIBUTIONS.md:1: url: 'https://example.org'",
        "eval_tasks/t/setup/app.py:1: url: 'https://api.example.org\"'",
        "eval_tasks/t/solution/transcript.md:1: plugin-marker: 'Arjan'",
        "eval_tasks/t/task.toml:1: url: 'www.example.org\"'",
        "precommit/config.yaml.j2:1: url: 'https://example.org/hooks'",
        "rules/a.md:1: url: 'https://example.org'",
        "skills/s/scripts/run.py:1: plugin-marker: 'mktoronto'",
    ]
