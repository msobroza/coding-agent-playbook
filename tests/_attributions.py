"""Parse and check ``catalog/core/ATTRIBUTIONS.md``, the provenance map of vendored core (D31).

The file's shape (ADR 0004)::

    ## <source>                      one section per upstream source; the name is
    Commit: `<sha>`                  the suffix of its license copy, LICENSE.<source>
    Form: distilled ...              instead of a Commit: a source without an open
                                     license (prU D50), no pin, no license copy
    ### <skill>                      one sub-section per core skill holding its text
    | Upstream file | Core files | Changes |
    | `<upstream path>` | `<core path>`, ... | <the changes> |
    | `<upstream path>` | DROP | <the reason> |
    - `<core path>`                  a distilled file: credited by name, no vendored text
    ## Engine-written files
    ### <skill>
    - `<core path>`                  a file the engine wrote, with no upstream text

Core paths are relative to the skill directory; one ending in ``/`` covers every
file under that directory (an example app). A distilled source's rows credit files
that hold none of its text, so their targets stay engine-written or distilled. An
upstream file, vendored or distilled, may feed several skills (one row per skill).
:func:`attribution_errors` holds the D31 checks; the gates in
``tests/integration/test_core_attributions.py`` and ``test_core_license_copies.py`` run
them on the shipped tree.

Example: ``load_core_attributions().sources["python-best-practices"].commit``
-> ``"fa0d3f58afb8bf56c028bb559e0e7bc1538e079a"``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from tests._catalog import CORE_ROOT, CORE_SKILLS_ROOT, REPO_ROOT

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping
    from pathlib import Path, PurePath

#: D11: the upstream commit each source is vendored from.
SOURCE_PINS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "python-best-practices": "fa0d3f58afb8bf56c028bb559e0e7bc1538e079a",
        "python-clean-architecture": "9d627ca7bedbe0bb9e2fcf3c83d81814a6133dce",
    }
)
#: D19: the SHA-256 of each source's MIT notice; every copy is byte-identical.
#: python-best-practices: 1,078 bytes, Ludo Technologies LLC; python-clean-architecture:
#: 1,066 bytes, MKToronto.
LICENSE_SHA256: Final[Mapping[str, str]] = MappingProxyType(
    {
        "python-best-practices": "5f2aed106f011d7f40db3a248ada7456350188c72a2e3aa8768ef251415fdc5c",
        "python-clean-architecture": (
            "80c4860b8cedcb4efa41ef98e33e3e79a43314442444b3470c3d68cae66025f8"
        ),
    }
)
#: Where a license copy lives, inside a core skill directory.
LICENSE_DIR: Final = "references"
#: The heading of the per-skill lists of files with no upstream text.
ENGINE_WRITTEN_HEADING: Final = "Engine-written files"
#: The core-files cell of a row that maps an upstream file to nothing.
DROP: Final = "DROP"
#: The mapping action (D78(15)) of a rule written fresh, with no vendored text.
DISTILL: Final = "distill"

ATTRIBUTIONS_PATH: Final = CORE_ROOT / "ATTRIBUTIONS.md"
#: The per-skill mapping specs (``mapping-<skill>.md``) that name each rule's action.
MAPPING_SPECS_DIR: Final = REPO_ROOT / "specs" / "prU-core-python-skills"

_COMMIT_RE: Final = re.compile(r"^Commit: `([0-9a-f]+)`")
_DISTILLED_FORM_RE: Final = re.compile(r"^Form: distilled\b")
_BULLET_RE: Final = re.compile(r"^- `([^`]+)`$")
_BACKTICKED_RE: Final = re.compile(r"^`([^`]+)`$")
_TABLE_HEADER: Final = ("Upstream file", "Core files", "Changes")
#: A mapping spec's rule table: ``| `rules/<file>` | section | priority | action | ...``.
_SPEC_RULE_ROW_RE: Final = re.compile(r"^\| `(rules/[^`]+)` \|[^|]*\|[^|]*\| (\S+) \|")


def license_name(source: str) -> str:
    """The file name of ``source``'s license copy: ``license_name("x")`` -> ``"LICENSE.x"``."""
    return f"LICENSE.{source}"


def is_license_copy_path(rel: PurePath, sources: Iterable[str] = SOURCE_PINS) -> bool:
    """True when ``rel`` (relative to ``catalog/core/``) is a license copy's one home (D19).

    >>> is_license_copy_path(PurePath("skills/s/references/LICENSE.python-best-practices"))
    True
    >>> is_license_copy_path(PurePath("skills/s/LICENSE.python-best-practices"))
    False
    """
    parts = rel.parts
    return (
        len(parts) == 4
        and parts[0] == CORE_SKILLS_ROOT.name
        and parts[2] == LICENSE_DIR
        and parts[3] in {license_name(source) for source in sources}
    )


def write_tree(root: Path, tree: Mapping[str, bytes | str]) -> None:
    """Write ``{relative path: body}`` under ``root``, creating parent dirs (synthetic trees)."""
    for rel, body in tree.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body.encode("utf-8") if isinstance(body, str) else body)


@dataclass(frozen=True)
class MappingRow:
    """One table row: an upstream file, the core files it became (none when dropped)."""

    upstream: str
    targets: tuple[str, ...]
    changes: str

    @property
    def dropped(self) -> bool:
        """True for a DROP row: the upstream file became no core file."""
        return not self.targets


@dataclass(frozen=True)
class SkillMapping:
    """One source's sub-section for one core skill."""

    rows: tuple[MappingRow, ...] = ()
    distilled: tuple[str, ...] = ()


@dataclass(frozen=True)
class Source:
    """One upstream source: its pinned commit and its per-skill mappings."""

    name: str
    commit: str | None
    skills: Mapping[str, SkillMapping]
    distilled: bool = False


@dataclass(frozen=True)
class Attributions:
    """The whole file: the sources and each skill's engine-written files."""

    sources: Mapping[str, Source]
    engine_written: Mapping[str, tuple[str, ...]]


def _where(lineno: int) -> str:
    return f"{ATTRIBUTIONS_PATH.name}:{lineno}"


def _row_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _backticked_path(cell: str, lineno: int) -> str:
    match = _BACKTICKED_RE.match(cell)
    if match is None:
        raise ValueError(f"{_where(lineno)}: expected one `path` in backticks, got {cell!r}")
    return match.group(1)


def _parse_row(line: str, lineno: int) -> MappingRow:
    cells = _row_cells(line)
    if len(cells) != len(_TABLE_HEADER):
        raise ValueError(f"{_where(lineno)}: a mapping row needs 3 cells: {line!r}")
    upstream, core, changes = cells
    targets = () if core == DROP else tuple(core.split(","))
    return MappingRow(
        _backticked_path(upstream, lineno),
        tuple(_backticked_path(part.strip(), lineno) for part in targets),
        changes,
    )


@dataclass
class _Parser:
    """The parse state: the current section (a source or the engine list) and skill."""

    commits: dict[str, str | None] = field(default_factory=dict)
    distilled: set[str] = field(default_factory=set)
    rows: dict[str, dict[str, list[MappingRow]]] = field(default_factory=dict)
    bullets: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    section: str | None = None
    skill: str | None = None

    def feed(self, line: str, lineno: int) -> None:
        """Route one line to its handler; prose lines are ignored."""
        if line.startswith("## "):
            self._section(line[3:].strip())
        elif line.startswith("### "):
            self._skill(line[4:].strip(), lineno)
        elif commit := _COMMIT_RE.match(line):
            self._commit(commit.group(1), line, lineno)
        elif _DISTILLED_FORM_RE.match(line):
            self._distilled_form(line, lineno)
        elif line.startswith("|"):
            self._row(line, lineno)
        elif bullet := _BULLET_RE.match(line):
            self._bullet(bullet.group(1), line, lineno)

    def _in_source(self) -> bool:
        return self.section is not None and self.section != ENGINE_WRITTEN_HEADING

    def _section(self, heading: str) -> None:
        self.section, self.skill = heading, None
        self.bullets.setdefault(heading, {})
        if heading != ENGINE_WRITTEN_HEADING:
            self.commits.setdefault(heading, None)
            self.rows.setdefault(heading, {})

    def _skill(self, skill: str, lineno: int) -> None:
        if self.section is None:
            raise ValueError(f"{_where(lineno)}: skill heading {skill!r} before any section")
        self.skill = skill
        self.bullets[self.section].setdefault(skill, [])
        if self._in_source():
            self.rows[self.section].setdefault(skill, [])

    def _commit(self, sha: str, line: str, lineno: int) -> None:
        if not self._in_source() or self.skill is not None:
            raise ValueError(f"{_where(lineno)}: a Commit line belongs under a source: {line!r}")
        self.commits[str(self.section)] = sha

    def _distilled_form(self, line: str, lineno: int) -> None:
        if not self._in_source() or self.skill is not None:
            raise ValueError(f"{_where(lineno)}: a Form line belongs under a source: {line!r}")
        self.distilled.add(str(self.section))

    def _row(self, line: str, lineno: int) -> None:
        cells = _row_cells(line)
        if tuple(cells) == _TABLE_HEADER or set("".join(cells)) <= {"-", " "}:
            return
        if not self._in_source() or self.skill is None:
            raise ValueError(f"{_where(lineno)}: a table row outside a source's skill: {line!r}")
        self.rows[str(self.section)][self.skill].append(_parse_row(line, lineno))

    def _bullet(self, path: str, line: str, lineno: int) -> None:
        if self.section is None or self.skill is None:
            raise ValueError(f"{_where(lineno)}: a listed file outside a skill: {line!r}")
        self.bullets[self.section][self.skill].append(path)

    def result(self) -> Attributions:
        """The parsed file, frozen."""
        sources = {
            name: Source(
                name,
                commit,
                MappingProxyType(
                    {
                        skill: SkillMapping(tuple(rows), tuple(self.bullets[name][skill]))
                        for skill, rows in self.rows[name].items()
                    }
                ),
                distilled=name in self.distilled,
            )
            for name, commit in self.commits.items()
        }
        engine = self.bullets.get(ENGINE_WRITTEN_HEADING, {})
        return Attributions(
            MappingProxyType(sources),
            MappingProxyType({skill: tuple(paths) for skill, paths in engine.items()}),
        )


def parse_attributions(text: str) -> Attributions:
    """Parse the ATTRIBUTIONS.md mapping format.

    A malformed row, a row or listed file outside a skill sub-section, or a
    misplaced ``Commit:`` line raises ``ValueError`` naming the line.
    """
    parser = _Parser()
    for lineno, line in enumerate(text.splitlines(), start=1):
        parser.feed(line, lineno)
    return parser.result()


def load_core_attributions() -> Attributions:
    """The shipped ``catalog/core/ATTRIBUTIONS.md``, parsed."""
    return parse_attributions(ATTRIBUTIONS_PATH.read_text(encoding="utf-8"))


def _skill_files(skill_dir: Path, sources: Iterable[str]) -> set[str]:
    """Every file of ``skill_dir`` (POSIX, relative), license copies and tool caches aside."""
    licenses = {f"{LICENSE_DIR}/{license_name(source)}" for source in sources}
    files = set()
    for path in skill_dir.rglob("*"):
        parts = path.relative_to(skill_dir).parts
        if not path.is_file() or any(p.startswith(".") or p == "__pycache__" for p in parts):
            continue
        files.add("/".join(parts))
    return files - licenses


def _listed_path_covers(listed: str, rel: str) -> bool:
    """True when the listed core path is ``rel`` or, ending in ``/``, a directory above it."""
    return rel.startswith(listed) if listed.endswith("/") else rel == listed


def _listed_path_exists(skill_dir: Path, listed: str) -> bool:
    """True when ``listed`` names a file of ``skill_dir`` or, ending in ``/``, a directory."""
    path = skill_dir / listed
    return path.is_dir() if listed.endswith("/") else path.is_file()


def _pin_errors(parsed: Attributions, pins: Mapping[str, str]) -> list[str]:
    errors = [
        f"{name}: no section for this pinned source" for name in pins if name not in parsed.sources
    ]
    for name, source in parsed.sources.items():
        if source.distilled:
            if source.commit is not None:
                errors.append(f"{name}: a distilled source carries no commit pin")
        elif name not in pins:
            errors.append(f"{name}: a source without a D11 pin")
        elif source.commit != pins[name]:
            errors.append(f"{name}: commit {source.commit} does not match the D11 pin {pins[name]}")
    return errors


def _row_errors(parsed: Attributions) -> list[str]:
    errors = []
    for name, source in parsed.sources.items():
        # An upstream file (vendored or distilled) has one row per skill it feeds.
        seen: set[tuple[str, str]] = set()
        for skill, mapping in source.skills.items():
            for row in mapping.rows:
                if (skill, row.upstream) in seen:
                    where = f"{name}/{skill}" if source.distilled else name
                    errors.append(f"{where}: `{row.upstream}` appears in more than one row")
                seen.add((skill, row.upstream))
                if not row.changes:
                    missing = "is dropped without a reason" if row.dropped else "lists no changes"
                    errors.append(f"{name}/{skill}: `{row.upstream}` {missing}")
    return errors


def _mappings(parsed: Attributions, skill: str, *, distilled: bool = False) -> list[SkillMapping]:
    """Every vendored (or, with ``distilled``, every distilled) source's sub-section for ``skill``."""
    return [
        source.skills[skill]
        for source in parsed.sources.values()
        if skill in source.skills and source.distilled == distilled
    ]


def _row_targets(parsed: Attributions, skill: str, *, distilled: bool = False) -> set[str]:
    """Every core path of ``skill`` that a vendored source's row maps upstream text to.

    With ``distilled``, the paths a distilled source's rows credit instead: they hold
    no upstream text.
    """
    mappings = _mappings(parsed, skill, distilled=distilled)
    return {t for m in mappings for row in m.rows for t in row.targets}


def _skill_coverage_errors(
    parsed: Attributions, skill: str, skill_dir: Path, sources: Iterable[str]
) -> list[str]:
    targets = _row_targets(parsed, skill)
    distilled = {path for m in _mappings(parsed, skill) for path in m.distilled}
    engine = set(parsed.engine_written.get(skill, ()))
    credited = _row_targets(parsed, skill, distilled=True)
    listed = targets | distilled | engine | credited
    if not skill_dir.is_dir() and not listed:
        return []  # A lane seeds an empty sub-section before it creates the skill.
    if not skill_dir.is_dir():
        return [f"{skill}: ATTRIBUTIONS.md lists its files, but core ships no such skill"]
    errors = [
        f"{skill}/{path}: listed in ATTRIBUTIONS.md but not in the skill"
        for path in sorted(listed)
        if not _listed_path_exists(skill_dir, path)
    ]
    errors += [
        f"{skill}/{path}: listed as engine-written and as holding upstream text"
        for path in sorted(engine & (targets | distilled))
    ]
    errors += [
        f"{skill}/{path}: listed as distilled and as a mapping target with a change list"
        for path in sorted(distilled & targets)
    ]
    errors += [
        f"{skill}/{path}: credited to a distilled source but not listed as engine-written"
        " or distilled"
        for path in sorted(credited - engine - distilled)
    ]
    errors += [
        f"{skill}/{rel}: neither a mapping target nor engine-written in ATTRIBUTIONS.md"
        for rel in sorted(_skill_files(skill_dir, sources))
        if not any(_listed_path_covers(path, rel) for path in listed)
    ]
    return errors


def _coverage_errors(parsed: Attributions, skills_root: Path, sources: Iterable[str]) -> list[str]:
    on_disk = {p.name for p in skills_root.iterdir() if p.is_dir()}
    listed_skills = set(parsed.engine_written).union(
        *(source.skills for source in parsed.sources.values())
    )
    errors = []
    for skill in sorted(on_disk | listed_skills):
        errors += _skill_coverage_errors(parsed, skill, skills_root / skill, sources)
    return errors


def _license_errors(parsed: Attributions, skills_root: Path, sources: Iterable[str]) -> list[str]:
    """A skill ships a source's license copy exactly when it holds that source's text.

    Whether the copy is byte-identical is :func:`license_copy_errors`' job alone.
    """
    errors = []
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        skill = skill_dir.name
        for source in sources:
            name = f"{LICENSE_DIR}/{license_name(source)}"
            mapping = parsed.sources[source].skills.get(skill) if source in parsed.sources else None
            has_text = mapping is not None and any(not row.dropped for row in mapping.rows)
            ships_copy = (skill_dir / name).is_file()
            if has_text and not ships_copy:
                errors.append(f"{skill}: holds text from {source} but ships no {name}")
            elif ships_copy and not has_text:
                errors.append(f"{skill}: ships {name} but holds no text from {source}")
    return errors


def license_copy_errors(
    core_root: Path = CORE_ROOT, license_sha256: Mapping[str, str] = LICENSE_SHA256
) -> list[str]:
    """Every license copy under ``core_root`` that is changed or out of place (D19).

    A file is a copy of a source's notice when it carries the copy's name or the
    notice's bytes; it belongs only at ``skills/<skill>/references/LICENSE.<source>``,
    byte-identical. ``[]`` means every copy is where it belongs.
    """
    by_name = {license_name(source): source for source in license_sha256}
    by_hash = {sha256: source for source, sha256 in license_sha256.items()}
    errors = []
    for path in sorted(p for p in core_root.rglob("*") if p.is_file()):
        rel = path.relative_to(core_root)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        source = by_name.get(rel.name) or by_hash.get(digest)
        if source is None:
            continue
        if not is_license_copy_path(rel, (source,)):
            errors.append(
                f"{rel.as_posix()}: {source}'s license copy belongs only at "
                f"{CORE_SKILLS_ROOT.name}/<skill>/{LICENSE_DIR}/{license_name(source)}"
            )
        elif digest != license_sha256[source]:
            errors.append(f"{rel.as_posix()}: not byte-identical to {source}'s license")
    return errors


def attribution_errors(
    parsed: Attributions,
    skills_root: Path = CORE_SKILLS_ROOT,
    *,
    pins: Mapping[str, str] = SOURCE_PINS,
    sources: Collection[str] = SOURCE_PINS,
) -> list[str]:
    """Every D31 violation of ``parsed`` against the core skill tree at ``skills_root``.

    Pins equal D11 (a distilled source, prU D50, carries none); every skill file (license copies aside) is a mapping target,
    distilled or engine-written, and every listed file exists; a skill listing
    files exists; no file is both engine-written and vendored, nor both distilled
    and a mapping target (D78(15)); an upstream file appears in at most one row per
    source; every row says what changed or, for DROP, why; a skill holding a
    source's text ships that source's license copy, and no copy ships without that
    text. ``[]`` means the map is complete.
    """
    return (
        _pin_errors(parsed, pins)
        + _row_errors(parsed)
        + _coverage_errors(parsed, skills_root, sources)
        + _license_errors(parsed, skills_root, sources)
    )


def distill_actions(spec_dir: Path = MAPPING_SPECS_DIR) -> dict[str, frozenset[str]]:
    """Skill -> the rule files its ``mapping-<skill>.md`` gives the ``distill`` action (D78(15)).

    Example: ``"rules/python-comments-why.md" in distill_actions()["python-coding"]`` -> ``True``.
    """
    actions: dict[str, frozenset[str]] = {}
    for spec in sorted(spec_dir.glob("mapping-*.md")):
        rows = (_SPEC_RULE_ROW_RE.match(line) for line in spec.read_text("utf-8").splitlines())
        skill = spec.stem.removeprefix("mapping-")
        actions[skill] = frozenset(row.group(1) for row in rows if row and row[2] == DISTILL)
    return actions


def distill_action_errors(
    parsed: Attributions, actions: Mapping[str, Collection[str]]
) -> list[str]:
    """Every rule the mapping spec distills that ATTRIBUTIONS.md maps with a change list (D78(15)).

    A distilled rule holds no upstream text, so it is listed as distilled or
    engine-written, never as a table row's target; a ``.md.j2`` target matches its
    ``.md`` spec name.
    """
    errors = []
    for skill, paths in sorted(actions.items()):
        targets = {t.removesuffix(".j2") for t in _row_targets(parsed, skill)}
        errors += [
            f"{skill}/{path}: the mapping spec distills it, but a table row maps upstream text to it"
            for path in sorted(paths)
            if path in targets
        ]
    return errors
