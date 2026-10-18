"""CI gate: every shipped resource is self-contained (no URLs, no plugin markers).

The engine's artifacts load straight into an agent's context, often in an
air-gapped deployment, so a rule, prompt or skill must never point outside the
shipped bundle and must never name the third-party source some of them were
distilled from. Credit for that source lives only in a layer root's
``ATTRIBUTIONS.md``: ``catalog/core/ATTRIBUTIONS.md`` for the engine's own
artifacts and ``catalog/plugins/<name>/ATTRIBUTIONS.md`` for a bundled plugin
(today the distilled ``python_design``).
The PR-L link gate (``links.py``) cannot enforce this: it recognizes only
markdown link syntax, masks code spans, and reads only ``.md``/``.md.j2``. This
scan applies no masking and reads every text file.

Scope: every file under ``catalog/core/`` (ids relative to it) and every file of
every bundled plugin under ``catalog/plugins/`` (its kind directories plus root
files such as ``README.md`` and ``ATTRIBUTIONS.md``; ids are prefixed
``plugins/<name>/``, its path relative to ``catalog/``), dot dirs and bytecode
caches aside. The plugin set is the directory listing, never a list of names, so
a new plugin is scanned with no edit here (acceptance 5). The one exception is
:data:`_VENDORED_PLUGIN_GATES`, the commented allowlist of vendored plugins whose
upstream text has known, reviewed exceptions; each entry names the dedicated
gate that covers it instead. The engine's pre-commit template (ids prefixed
``templates/precommit/``) ships too and gets both checks. A plugin's files are
all fully scanned except its root ``ATTRIBUTIONS.md``, which is URL-free but may
name its source (:func:`plugin_policy_for`). For ``catalog/core/`` the checks
are decided per file by :func:`policy_for`:

* by default -> URLs and plugin markers are both violations. That includes the
  eval fixtures under ``eval_tasks/<id>/setup/`` and ``solution/``: they ship in
  the wheel and are copied into the agent's scratch repo. No fixture needs a URL
  today; if one ever does, allow only a reserved example host (``example.com``,
  ``*.test``, ``*.invalid``, ``localhost``) for that one path;
* ``catalog/core/ATTRIBUTIONS.md`` -> URL-free, but it *must* name the plugin, so
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

from tests._catalog import (
    CORE_ROOT,
    PRECOMMIT_TEMPLATE_DIR,
    REPO_ROOT,
    bundled_plugin_dirs,
    plugin_files_root,
)

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.catalog

#: Every bundled plugin's ids start here: its path relative to ``catalog/``.
_PLUGINS_PREFIX = "plugins/"
#: The distilled opt-in plugin (SPEC §11.5.2), whose ``ATTRIBUTIONS.md`` must credit the source.
_PYTHON_DESIGN_ROOT = plugin_files_root("python_design")
_PYTHON_DESIGN_PREFIX = f"{_PLUGINS_PREFIX}python_design/"
#: The one allowlist: vendored bundled plugins this scan skips, each mapped to the
#: dedicated gate (a test file) that covers it instead. Every other directory under
#: ``catalog/plugins/`` is scanned. Add an entry only for vendored upstream text
#: with known, reviewed exceptions, and only when the named gate scans every file
#: of the plugin for URLs.
#: * ``superpowers``: its upstream markdown legitimately holds bare-domain URLs in
#:   code samples (``api.example.com/v1/messages``), which the bare-domain branch of
#:   :data:`_URL_RE` flags and which must stay byte-identical. Its gate scans every
#:   file for ``scheme://``, ``mailto:`` and ``www.`` URLs and for
#:   ``superpowers:<skill>`` references, and its skills for upstream-plugin markers.
_VENDORED_PLUGIN_GATES: dict[str, str] = {
    "superpowers": "tests/plugins/test_superpowers_self_contained.py",
}
#: The engine-owned pre-commit template (engine wiring, not content) ships too.
_PRECOMMIT_TEMPLATE_PREFIX = "templates/precommit/"

#: The python-best-practices commit core's distilled rules were written from (spec 9.1).
_PBP_COMMIT = "bf64c51d2f4c8255f126c98359bdbcd5e2587b92"

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
#: And the python-best-practices collection that core distills (its name, its
#: publisher, and the publisher's analyzer, which D8 drops); plain "best
#: practices" and a "ludo" board game stay clean.
_PLUGIN_MARKER_RE = re.compile(
    r"(?i)python[\s_-]*clean[\s_-]*architecture|\barjan|\bmk[\s_-]*toronto"
    r"|software[\s_-]*designer[\s_-]*mindset|claude_plugin_root|\.claude/plugins"
    r"|python[\s_-]*best[\s_-]*practices|\bludo[\s_-]*technologies|\bpyscn\b"
)


@dataclass(frozen=True)
class ScanPolicy:
    """Which checks apply to one file."""

    urls: bool
    markers: bool


@dataclass(frozen=True)
class ScanTarget:
    """One file to scan, its id (prefix + path relative to its scan root), and its policy."""

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
    """Return the checks for ``rel`` (a path relative to ``catalog/core/``).

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


def plugin_policy_for(rel: Path) -> ScanPolicy:
    """Return the checks for ``rel`` (a path relative to a bundled plugin's root).

    The plugin's own root ``ATTRIBUTIONS.md`` is its one sanctioned home of the
    credit; every other plugin file (skills, scripts, references, README) gets
    both checks.

    >>> plugin_policy_for(Path("ATTRIBUTIONS.md"))
    ScanPolicy(urls=True, markers=False)
    """
    return ScanPolicy(urls=True, markers=rel != Path(_ATTRIBUTIONS_NAME))


def _scanned_plugin_dirs() -> list[Path]:
    """Every bundled plugin directory except the allowlisted vendored ones."""
    return [path for path in bundled_plugin_dirs() if path.name not in _VENDORED_PLUGIN_GATES]


def _plugin_prefix(plugin_dir: Path) -> str:
    """The id prefix of ``plugin_dir``'s files: ``plugins/<name>/``."""
    return f"{_PLUGINS_PREFIX}{plugin_dir.name}/"


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

        scan_targets(plugin_dir, prefix="plugins/python_design/", policy=plugin_policy_for)
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


_TARGETS = (
    scan_targets(CORE_ROOT)
    + [
        target
        for plugin_dir in _scanned_plugin_dirs()
        for target in scan_targets(
            plugin_dir, prefix=_plugin_prefix(plugin_dir), policy=plugin_policy_for
        )
    ]
    + scan_targets(
        PRECOMMIT_TEMPLATE_DIR,
        prefix=_PRECOMMIT_TEMPLATE_PREFIX,
        policy=lambda _: ScanPolicy(urls=True, markers=True),
    )
)


@pytest.mark.parametrize("target", _TARGETS, ids=lambda t: t.rel)
def test_shipped_resource_is_self_contained(target: ScanTarget) -> None:
    violations = scan_file(target)
    assert violations == [], (
        "shipped resources must carry no URLs and must not name the plugin they were "
        "distilled from (credit lives only in core/ATTRIBUTIONS.md and a bundled "
        f"plugin's root {_ATTRIBUTIONS_NAME}):\n" + "\n".join(v.render() for v in violations)
    )


def test_scan_covers_every_artifact_kind() -> None:
    """Guard against a walker that silently scans nothing."""
    rels = {t.rel for t in _TARGETS}
    for prefix in (
        "rules/",
        "prompts/",
        _PRECOMMIT_TEMPLATE_PREFIX,
        f"{_PYTHON_DESIGN_PREFIX}skills/",
    ):
        assert any(r.startswith(prefix) for r in rels), f"nothing scanned under {prefix}"
    for part in ("/task.toml", "/setup/", "/solution/"):
        assert any(part in r for r in rels), f"no eval-task file matching {part} scanned"
    assert _ATTRIBUTIONS_NAME in rels
    assert f"{_EVAL_TASKS_SUBDIR}/{_ATTRIBUTIONS_NAME}" in rels
    assert f"{_PYTHON_DESIGN_PREFIX}{_ATTRIBUTIONS_NAME}" in rels
    # The plugin's README ships in the wheel; its enable instructions must name
    # neither a URL nor the source plugin.
    assert f"{_PYTHON_DESIGN_PREFIX}README.md" in rels


def test_scan_covers_every_bundled_plugin_but_the_allowlisted_vendored_ones() -> None:
    """Acceptance 5: a new ``catalog/plugins/<name>/`` is scanned with no edit here."""
    scanned = {t.rel.split("/")[1] for t in _TARGETS if t.rel.startswith(_PLUGINS_PREFIX)}
    on_disk = {path.name for path in bundled_plugin_dirs()}
    assert scanned == on_disk - set(_VENDORED_PLUGIN_GATES)


@pytest.mark.parametrize(("plugin", "gate"), sorted(_VENDORED_PLUGIN_GATES.items()))
def test_each_allowlisted_vendored_plugin_ships_and_names_a_live_gate(
    plugin: str, gate: str
) -> None:
    """A stale allowlist entry fails: the plugin must exist, and so must its gate."""
    assert plugin_files_root(plugin).is_dir(), f"allowlisted plugin {plugin!r} is not shipped"
    assert (REPO_ROOT / gate).is_file(), f"{plugin!r}'s dedicated gate {gate} does not exist"


def test_plugin_scan_exempts_only_each_plugin_root_attributions_from_the_marker_check() -> None:
    plugin_targets = [t for t in _TARGETS if t.rel.startswith(_PLUGINS_PREFIX)]
    exempt = {t.rel for t in plugin_targets if t.policy != ScanPolicy(urls=True, markers=True)}
    assert exempt == {
        f"{_plugin_prefix(path)}{_ATTRIBUTIONS_NAME}"
        for path in _scanned_plugin_dirs()
        if (path / _ATTRIBUTIONS_NAME).is_file()
    }
    assert f"{_PYTHON_DESIGN_PREFIX}{_ATTRIBUTIONS_NAME}" in exempt


@pytest.mark.parametrize(
    "attributions",
    [CORE_ROOT / _ATTRIBUTIONS_NAME, _PYTHON_DESIGN_ROOT / _ATTRIBUTIONS_NAME],
    ids=["core", "python_design"],
)
def test_attributions_credit_the_distilled_source(attributions: Path) -> None:
    text = attributions.read_text(encoding="utf-8")
    assert "python-clean-architecture" in text
    assert "MKToronto" in text
    assert "MIT" in text


def test_core_attributions_credit_python_best_practices() -> None:
    """Core's second distilled source: its name, publisher, pinned commit and license."""
    text = (CORE_ROOT / _ATTRIBUTIONS_NAME).read_text(encoding="utf-8")
    for needle in ("python-best-practices", "Ludo Technologies LLC", _PBP_COMMIT, "MIT"):
        assert needle in text, f"core ATTRIBUTIONS.md must credit {needle!r}"


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
        ("Distilled from python-best-practices.", "plugin-marker", "python-best-practices"),
        ("Python Best Practices skills", "plugin-marker", "Python Best Practices"),
        ("Copyright (c) 2026 Ludo Technologies LLC", "plugin-marker", "Ludo Technologies"),
        ("Run pyscn check before merging.", "plugin-marker", "pyscn"),
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
        "Follow these best practices for fixtures.\nThe ludo board game is fine.\n"
    )
    assert scan_text(clean, "x.md", _BOTH) == []


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("rules/languages/python/pure-core.md", ScanPolicy(urls=True, markers=True)),
        ("prompts/characterize.md", ScanPolicy(urls=True, markers=True)),
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
        ("README.md", ScanPolicy(urls=True, markers=True)),
        ("skills/s/SKILL.md", ScanPolicy(urls=True, markers=True)),
        ("skills/s/scripts/run.py", ScanPolicy(urls=True, markers=True)),
        ("skills/s/references/ATTRIBUTIONS.md", ScanPolicy(urls=True, markers=True)),
    ],
)
def test_plugin_policy_for(rel: str, expected: ScanPolicy) -> None:
    assert plugin_policy_for(Path(rel)) == expected


def test_plugin_scan_targets_on_a_synthetic_tree(tmp_path: Path) -> None:
    """Plugin ids carry the prefix; only the plugin-root ATTRIBUTIONS.md may name the source."""
    files = {
        "ATTRIBUTIONS.md": "Credit: python-clean-architecture (MIT).\n",
        "README.md": "See www.example.org.\n",
        "skills/s/SKILL.md": "As Arjan teaches.\n",
        "skills/s/__pycache__/x.pyc": "https://example.org\n",
    }
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")

    targets = scan_targets(tmp_path, prefix="plugins/p/", policy=plugin_policy_for)
    violations = [v.render() for t in targets for v in scan_file(t)]

    assert violations == [
        "plugins/p/README.md:1: url: 'www.example.org.'",
        "plugins/p/skills/s/SKILL.md:1: plugin-marker: 'Arjan'",
    ]


def test_scan_targets_on_a_synthetic_tree(tmp_path: Path) -> None:
    """Every file is scanned, fixtures included; only attribution notes are exempt."""
    files = {
        "ATTRIBUTIONS.md": "Credit: python-clean-architecture.\n",
        "rules/a.md": "Read https://example.org first.\n",
        "prompts/p.md.j2": "clean\n",
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
        "rules/a.md:1: url: 'https://example.org'",
        "skills/s/scripts/run.py:1: plugin-marker: 'mktoronto'",
    ]
