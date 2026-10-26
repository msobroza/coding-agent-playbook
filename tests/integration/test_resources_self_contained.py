"""CI gate: every shipped resource is self-contained (no URLs, no plugin markers).

The engine's artifacts load straight into an agent's context, often in an
air-gapped deployment, so a rule, prompt or skill must never point outside the
shipped bundle and must never name the third-party source some of them were
vendored or distilled from. Credit for that source lives only in a layer root's
``ATTRIBUTIONS.md``: ``catalog/core/ATTRIBUTIONS.md`` for the engine's own
artifacts and ``catalog/plugins/<name>/ATTRIBUTIONS.md`` for a bundled plugin.
The PR-L link gate (``validation/link_check.py``) cannot enforce this: it recognizes only
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
  eval fixtures under ``eval_samples/<prompt>/<name>/setup/`` and ``solution/``: they ship in
  the wheel and are copied into the agent's scratch repo. No fixture needs a URL
  today; if one ever does, allow only a reserved example host (``example.com``,
  ``*.test``, ``*.invalid``, ``localhost``) for that one path;
* ``catalog/core/ATTRIBUTIONS.md`` -> URL-free, but it *must* name both vendored
  sources (ADR 0004), so the marker scan is off;
* ``skills/<skill>/references/LICENSE.python-best-practices`` and
  ``LICENSE.python-clean-architecture`` -> the byte-identical MIT notices (D19)
  name their source, so the marker scan is off there and nowhere else; URLs are
  still scanned, except in ``LICENSE.simple-agent-api`` (D64), whose Apache-2.0
  text cites the license's own address. ``test_core_license_copies.py`` pins
  their bytes and places;
* markdown under ``skills/`` -> a reserved example host (D38: ``example.com``,
  ``.org``, ``.net`` and their subdomains, ``*.test``, ``*.example``,
  ``*.invalid``, ``localhost``, the bare host ``test``; any scheme) passes inside
  a fenced code block; prose stays URL-free. Python under ``skills/<skill>/examples/``
  may name a reserved host anywhere (D78(13)); every other host still fails;
* ``eval_samples/**/ATTRIBUTIONS.md`` outside fixture trees -> markers only: the
  CC BY 4.0 licence requires its licence URI (pinned by
  ``test_crosscommitvuln_fixtures.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pytest

from tests._attributions import (
    SOURCE_PINS,
    is_license_copy_path,
    load_core_attributions,
    write_tree,
)
from tests._catalog import (
    CORE_ROOT,
    CORE_SKILLS_ROOT,
    MARKDOWN_SUFFIXES,
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
#: A bundled plugin this scan must reach (not allowlisted below): the coverage guards
#: check that its skills, root ``ATTRIBUTIONS.md`` and ``README.md`` are all scanned.
_SCANNED_PLUGIN_PREFIX = f"{_PLUGINS_PREFIX}mattpocock_skills/"
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

_EXAMPLES_SUBDIR = "examples"
#: License copies whose pinned text (D19, D64) cites a URL: the Apache-2.0 notice
#: of the vendored agent example names the Apache license's address.
_LICENSE_COPIES_CITING_A_URL = frozenset({"LICENSE.simple-agent-api"})

_EVAL_SAMPLES_SUBDIR = "eval_samples"
#: Per-sample fixture trees: ``eval_samples/<prompt>/<name>/{setup,solution}/**``.
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
#: A fenced code block's opening or closing line: three or more backticks or tildes.
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
#: The host of a URL match: after the scheme (and any user info), after ``mailto:``'s
#: ``@``, after ``git@``, or the bare domain itself.
_HOST_RE = re.compile(
    r"(?i)^(?:[a-z][a-z0-9+.-]*://(?:[^/@\s]*@)?|mailto:[^@\s]*@|git@)?([a-z0-9.-]*)"
)
#: D38's reserved names: the bare hosts, and the domains whose subdomains also pass.
_RESERVED_HOSTS = frozenset({"localhost", "test", "example.com", "example.org", "example.net"})
_RESERVED_SUFFIXES = (
    ".example.com",
    ".example.org",
    ".example.net",
    ".test",
    ".example",
    ".invalid",
)

#: Where a reserved example host may appear in a file: nowhere, inside fenced code
#: blocks only (a core skill's markdown), or anywhere (a core example's Python code).
ReservedHosts = Literal["never", "in-fences", "anywhere"]


@dataclass(frozen=True)
class ScanPolicy:
    """Which checks apply to one file."""

    urls: bool
    markers: bool
    reserved_hosts: ReservedHosts = "never"


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
    ScanPolicy(urls=True, markers=False, reserved_hosts='never')
    """
    if rel == Path(_ATTRIBUTIONS_NAME):
        # The one sanctioned home of the credit: it names both sources by design.
        return ScanPolicy(urls=True, markers=False)
    if (
        rel.name == _ATTRIBUTIONS_NAME
        and rel.parts[0] == _EVAL_SAMPLES_SUBDIR
        and not _is_fixture(rel)
    ):
        # CC BY 4.0 requires the licence URI next to the derived fixtures.
        return ScanPolicy(urls=False, markers=True)
    if rel.parts[0] == CORE_SKILLS_ROOT.name:
        return _skill_policy(rel)
    return ScanPolicy(urls=True, markers=True)


def _skill_policy(rel: Path) -> ScanPolicy:
    """The checks for a file under ``skills/``: license copies, D38 and D78(13)."""
    parts = rel.parts
    if is_license_copy_path(rel):
        # D19: the byte-identical notice names its source. The Apache-2.0 text also
        # cites its own license URL; its bytes are pinned, so nothing can slip in.
        return ScanPolicy(urls=rel.name not in _LICENSE_COPIES_CITING_A_URL, markers=False)
    if rel.name.endswith(MARKDOWN_SUFFIXES):
        return ScanPolicy(urls=True, markers=True, reserved_hosts="in-fences")
    if len(parts) > 3 and parts[2] == _EXAMPLES_SUBDIR and rel.suffix == ".py":
        return ScanPolicy(urls=True, markers=True, reserved_hosts="anywhere")
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
    """True for ``eval_samples/<prompt>/<name>/setup/**`` and ``.../<name>/solution/**``."""
    parts = rel.parts
    return len(parts) > 4 and parts[0] == _EVAL_SAMPLES_SUBDIR and parts[3] in _FIXTURE_DIRS


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

        scan_targets(plugin_dir, prefix="plugins/mattpocock_skills/", policy=plugin_policy_for)
    """
    # POSIX-style ids keep the test ids and prefix checks stable on Windows too.
    rels = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not _is_hidden(p, root)
    )
    assert rels, f"nothing scanned under {root}"
    return [ScanTarget(root / rel, prefix + rel, policy(Path(rel))) for rel in rels]


def _is_reserved(url: str) -> bool:
    """True when ``url``'s host is one of D38's reserved example names.

    >>> _is_reserved("https://api.example.com/v1"), _is_reserved("https://pypi.org/x")
    (True, False)
    """
    match = _HOST_RE.match(url)
    host = match.group(1).casefold().rstrip(".") if match else ""
    return host in _RESERVED_HOSTS or host.endswith(_RESERVED_SUFFIXES)


def _fenced_lines(lines: list[str]) -> set[int]:
    """The 1-based numbers of the lines inside fenced code blocks (fence lines excluded)."""
    fenced: set[int] = set()
    fence: str | None = None
    for lineno, line in enumerate(lines, start=1):
        marker = _FENCE_RE.match(line)
        if fence is None and marker:
            fence = marker.group(1)
        elif fence is not None and marker and marker.group(1).startswith(fence):
            fence = None
        elif fence is not None:
            fenced.add(lineno)
    return fenced


def scan_text(text: str, rel: str, policy: ScanPolicy) -> list[Violation]:
    """Return every URL / plugin-marker hit in ``text`` that ``policy`` forbids.

    >>> scan_text("see www.example.org", "r.md", ScanPolicy(urls=True, markers=True))
    [Violation(rel='r.md', line=1, kind='url', text='www.example.org')]
    """
    lines = text.splitlines()
    if policy.reserved_hosts == "in-fences":
        lenient = _fenced_lines(lines)
    elif policy.reserved_hosts == "anywhere":
        lenient = set(range(1, len(lines) + 1))
    else:
        lenient = set()
    found: list[Violation] = []
    for lineno, line in enumerate(lines, start=1):
        if policy.urls:
            found += [
                Violation(rel, lineno, "url", m.group(0))
                for m in _URL_RE.finditer(line)
                if not (lineno in lenient and _is_reserved(m.group(0)))
            ]
        if policy.markers:
            found += [
                Violation(rel, lineno, "plugin-marker", m.group(0))
                for m in _PLUGIN_MARKER_RE.finditer(line)
            ]
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
        f"{_SCANNED_PLUGIN_PREFIX}skills/",
    ):
        assert any(r.startswith(prefix) for r in rels), f"nothing scanned under {prefix}"
    for part in ("/sample.toml", "/setup/", "/solution/"):
        assert any(part in r for r in rels), f"no eval-sample file matching {part} scanned"
    assert _ATTRIBUTIONS_NAME in rels
    assert f"{_EVAL_SAMPLES_SUBDIR}/{_ATTRIBUTIONS_NAME}" in rels
    assert f"{_SCANNED_PLUGIN_PREFIX}{_ATTRIBUTIONS_NAME}" in rels
    # The plugin's README ships in the wheel; its enable instructions must name
    # neither a URL nor a distilled source.
    assert f"{_SCANNED_PLUGIN_PREFIX}README.md" in rels


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
    assert f"{_SCANNED_PLUGIN_PREFIX}{_ATTRIBUTIONS_NAME}" in exempt


@pytest.mark.parametrize(
    ("source", "credits"),
    [
        ("python-best-practices", ("Ludo Technologies LLC", "MIT License")),
        ("python-clean-architecture", ("MKToronto", "MIT License")),
        ("simple-agent-api", ("Domino Data Lab", "Apache License 2.0")),
    ],
)
def test_core_attributions_credit_each_vendored_source(
    source: str, credits: tuple[str, ...]
) -> None:
    """ADR 0004: each source has its own section, with its D11 pin, holder and license."""
    assert load_core_attributions().sources[source].commit == SOURCE_PINS[source]
    text = (CORE_ROOT / _ATTRIBUTIONS_NAME).read_text(encoding="utf-8")
    section = text.split(f"\n## {source}\n", 1)[1].split("\n## ", 1)[0]
    for needle in credits:
        assert needle in section, f"core ATTRIBUTIONS.md's {source} section must credit {needle!r}"


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


#: A core skill's markdown: reserved example hosts pass inside fenced code blocks (D38).
_SKILL_MD = ScanPolicy(urls=True, markers=True, reserved_hosts="in-fences")
#: Example app code under a core skill: reserved hosts pass anywhere in the file (D78(13)).
_EXAMPLE_PY = ScanPolicy(urls=True, markers=True, reserved_hosts="anywhere")
#: A byte-identical license copy names its source by design (D19).
_LICENSE_COPY = ScanPolicy(urls=True, markers=False)


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("skills/python-coding/rules/python-pure-core.md", _SKILL_MD),
        ("prompts/characterize.md", ScanPolicy(urls=True, markers=True)),
        ("eval_samples/review/some-sample/sample.toml", ScanPolicy(urls=True, markers=True)),
        ("eval_samples/review/some-sample/setup/app/db.py", ScanPolicy(urls=True, markers=True)),
        (
            "eval_samples/review/some-sample/solution/transcript.md",
            ScanPolicy(urls=True, markers=True),
        ),
        ("ATTRIBUTIONS.md", ScanPolicy(urls=True, markers=False)),
        ("eval_samples/ATTRIBUTIONS.md", ScanPolicy(urls=False, markers=True)),
        ("eval_samples/review/some-sample/ATTRIBUTIONS.md", ScanPolicy(urls=False, markers=True)),
        (
            "eval_samples/review/some-sample/setup/ATTRIBUTIONS.md",
            ScanPolicy(urls=True, markers=True),
        ),
        ("rules/ATTRIBUTIONS.md", ScanPolicy(urls=True, markers=True)),
        ("skills/s/SKILL.md", _SKILL_MD),
        ("skills/s/references/guide.md", _SKILL_MD),
        ("skills/s/examples/app/README.md", _SKILL_MD),
        ("skills/s/examples/app/src/app/main.py", _EXAMPLE_PY),
        ("skills/s/examples/app/pyproject.toml", ScanPolicy(urls=True, markers=True)),
        ("skills/s/scripts/tool.py", ScanPolicy(urls=True, markers=True)),
        ("skills/s/references/LICENSE.python-best-practices", _LICENSE_COPY),
        ("skills/s/references/LICENSE.python-clean-architecture", _LICENSE_COPY),
        ("skills/s/references/LICENSE.simple-agent-api", ScanPolicy(urls=False, markers=False)),
        ("skills/s/LICENSE.simple-agent-api", ScanPolicy(urls=True, markers=True)),
        ("skills/s/references/LICENSE.other-source", ScanPolicy(urls=True, markers=True)),
        ("skills/s/LICENSE.python-best-practices", ScanPolicy(urls=True, markers=True)),
        (
            "skills/s/references/x/LICENSE.python-best-practices",
            ScanPolicy(urls=True, markers=True),
        ),
        ("references/LICENSE.python-clean-architecture", ScanPolicy(urls=True, markers=True)),
        ("prompts/LICENSE.python-best-practices", ScanPolicy(urls=True, markers=True)),
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
        "eval_samples/ATTRIBUTIONS.md": "Licence: https://licence.example\n",
        "eval_samples/review/t/sample.toml": 'description = "see www.example.org"\n',
        "eval_samples/review/t/setup/app.py": 'URL = "https://api.example.org"\n',
        "eval_samples/review/t/setup/ATTRIBUTIONS.md": "https://example.org\n",
        "eval_samples/review/t/solution/transcript.md": "Adapted from Arjan's example.\n",
        "eval_samples/review/t/solution/negatives/wrong.md": "clean\n",
        "rules/.cache/junk.md": "https://example.org\n",
    }
    write_tree(tmp_path, files)

    violations = [v.render() for t in scan_targets(tmp_path) for v in scan_file(t)]

    assert violations == [
        "eval_samples/review/t/sample.toml:1: url: 'www.example.org\"'",
        "eval_samples/review/t/setup/ATTRIBUTIONS.md:1: url: 'https://example.org'",
        "eval_samples/review/t/setup/app.py:1: url: 'https://api.example.org\"'",
        "eval_samples/review/t/solution/transcript.md:1: plugin-marker: 'Arjan'",
        "rules/a.md:1: url: 'https://example.org'",
        "skills/s/scripts/run.py:1: plugin-marker: 'mktoronto'",
    ]


_FENCE = "```"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/v1/items",
        "http://api.example.org/x",
        "https://deep.sub.example.net",
        "http://localhost:8000/health",
        "postgresql://user:secret@localhost/app",
        "http://test/items",
        "https://svc.test/x",
        "https://shop.example/x",
        "https://nothing.invalid",
        "www.example.org/path",
        "mailto:someone@example.com",
        "api.example.com/v1",
    ],
)
def test_reserved_hosts_pass_inside_a_fence_of_a_skill_file(url: str) -> None:
    text = f'Prose.\n{_FENCE}python\nURL = "{url}"\n{_FENCE}\n'
    assert scan_text(text, "x.md", _SKILL_MD) == []


@pytest.mark.parametrize(
    "url",
    [
        "https://pypi.org/simple",
        "https://example.com.evil.org/x",
        "https://notexample.com/x",
        "http://localhost.evil.net/x",
        "https://example.co/x",
        "https://tester/x",
    ],
)
def test_other_hosts_still_fail_inside_a_fence(url: str) -> None:
    text = f'{_FENCE}python\nURL = "{url}"\n{_FENCE}\n'
    assert [v.kind for v in scan_text(text, "x.md", _SKILL_MD)] == ["url"]


def test_a_reserved_host_in_prose_still_fails() -> None:
    """D38: prose stays URL-free; only fenced code may name a reserved host."""
    text = f"See https://example.com/docs.\n{_FENCE}\nok\n{_FENCE}\nThen http://localhost:8000.\n"
    assert scan_text(text, "x.md", _SKILL_MD) == [
        Violation("x.md", 1, "url", "https://example.com/docs."),
        Violation("x.md", 5, "url", "http://localhost:8000."),
    ]


def test_a_tilde_fence_counts_and_an_unclosed_fence_runs_to_the_end() -> None:
    text = "~~~toml\nurl = 'https://example.com'\n~~~\nprose\n```\nhttp://localhost/x\n"
    assert scan_text(text, "x.md", _SKILL_MD) == []


def test_reserved_hosts_outside_skills_fail_even_in_a_fence() -> None:
    text = f"{_FENCE}\nhttps://example.com/x\n{_FENCE}\n"
    assert [v.kind for v in scan_text(text, "x.md", _BOTH)] == ["url"]


def test_example_code_may_name_a_reserved_host_anywhere() -> None:
    text = (
        'BASE = "http://localhost:8000"\n'
        'OTHER = "https://api.example.com/v1"\n'
        'BAD = "https://pypi.org/x"\n'
    )
    assert scan_text(text, "main.py", _EXAMPLE_PY) == [
        Violation("main.py", 3, "url", 'https://pypi.org/x"')
    ]


def test_a_license_copy_passes_the_marker_scan_only_in_a_skill_references_dir(
    tmp_path: Path,
) -> None:
    """D19: the two license names may name their source only at their sanctioned home."""
    notice = "MIT License\n\nCopyright (c) 2026 Ludo Technologies LLC\n"
    files = {
        "skills/s/references/LICENSE.python-best-practices": notice,
        "skills/s/LICENSE.python-best-practices": notice,
        "prompts/LICENSE.python-best-practices": notice,
    }
    write_tree(tmp_path, files)

    violations = [v.render() for t in scan_targets(tmp_path) for v in scan_file(t)]

    assert violations == [
        "prompts/LICENSE.python-best-practices:3: plugin-marker: 'Ludo Technologies'",
        "skills/s/LICENSE.python-best-practices:3: plugin-marker: 'Ludo Technologies'",
    ]
