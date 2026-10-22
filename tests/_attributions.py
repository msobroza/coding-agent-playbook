"""Parse and check ``catalog/core/ATTRIBUTIONS.md``, the provenance map of vendored core (D31).

The file's shape (ADR 0004)::

    ## <source>                      one section per upstream source; the name is
    Commit: `<sha>`                  the suffix of its license copy, LICENSE.<source>
    ### <skill>                      one sub-section per core skill holding its text
    | Upstream file | Core files | Changes |
    | `<upstream path>` | `<core path>`, ... | <the changes> |
    | `<upstream path>` | DROP | <the reason> |
    - `<core path>`                  a distilled file: credited by name, no vendored text
    ## Engine-written files
    ### <skill>
    - `<core path>`                  a file the engine wrote, with no upstream text

Core paths are relative to the skill directory; one ending in ``/`` covers every
file under that directory (an example app). :func:`attribution_errors` holds the
D31 checks; the gates in ``tests/integration/test_core_attributions.py`` and
``test_core_license_copies.py`` run them on the shipped tree.

Example: ``load_core_attributions().sources["python-best-practices"].commit``
-> ``"fa0d3f58afb8bf56c028bb559e0e7bc1538e079a"``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

#: D11: the upstream commit each source is vendored from.
SOURCE_PINS: Final[Mapping[str, str]] = {
    "python-best-practices": "fa0d3f58afb8bf56c028bb559e0e7bc1538e079a",
    "python-clean-architecture": "9d627ca7bedbe0bb9e2fcf3c83d81814a6133dce",
}
#: D19: the SHA-256 of each source's MIT notice; every copy is byte-identical.
#: python-best-practices: 1,078 bytes, Ludo Technologies LLC; python-clean-architecture:
#: 1,066 bytes, MKToronto.
LICENSE_SHA256: Final[Mapping[str, str]] = {
    "python-best-practices": "5f2aed106f011d7f40db3a248ada7456350188c72a2e3aa8768ef251415fdc5c",
    "python-clean-architecture": "80c4860b8cedcb4efa41ef98e33e3e79a43314442444b3470c3d68cae66025f8",
}
#: Where a license copy lives, inside a core skill directory.
LICENSE_DIR: Final = "references"
#: The heading of the per-skill lists of files with no upstream text.
ENGINE_WRITTEN_HEADING: Final = "Engine-written files"
#: The core-files cell of a row that maps an upstream file to nothing.
DROP: Final = "DROP"

ATTRIBUTIONS_PATH: Final = CORE_ROOT / "ATTRIBUTIONS.md"
CORE_SKILLS_ROOT: Final = CORE_ROOT / "skills"

_COMMIT_RE: Final = re.compile(r"^Commit: `([0-9a-f]+)`")
_BULLET_RE: Final = re.compile(r"^- `([^`]+)`$")
_CODE_RE: Final = re.compile(r"^`([^`]+)`$")
_TABLE_HEADER: Final = ("Upstream file", "Core files", "Changes")


def license_name(source: str) -> str:
    """The file name of ``source``'s license copy: ``license_name("x")`` -> ``"LICENSE.x"``."""
    return f"LICENSE.{source}"


@dataclass(frozen=True)
class MappingRow:
    """One table row: an upstream file, the core files it became (none when dropped)."""

    upstream: str
    targets: tuple[str, ...]
    dropped: bool
    changes: str


@dataclass
class SkillMapping:
    """One source's sub-section for one core skill."""

    rows: list[MappingRow] = field(default_factory=list)
    distilled: list[str] = field(default_factory=list)


@dataclass
class Source:
    """One upstream source: its pinned commit and its per-skill mappings."""

    name: str
    commit: str | None = None
    skills: dict[str, SkillMapping] = field(default_factory=dict)


@dataclass
class Attributions:
    """The whole file: the sources and each skill's engine-written files."""

    sources: dict[str, Source] = field(default_factory=dict)
    engine_written: dict[str, list[str]] = field(default_factory=dict)


def _row_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _code(cell: str, lineno: int) -> str:
    match = _CODE_RE.match(cell)
    if match is None:
        raise ValueError(
            f"ATTRIBUTIONS.md:{lineno}: expected one `path` in backticks, got {cell!r}"
        )
    return match.group(1)


def _parse_row(line: str, lineno: int) -> MappingRow:
    cells = _row_cells(line)
    if len(cells) != len(_TABLE_HEADER):
        raise ValueError(f"ATTRIBUTIONS.md:{lineno}: a mapping row needs 3 cells: {line!r}")
    upstream, core, changes = cells
    if core == DROP:
        return MappingRow(_code(upstream, lineno), (), dropped=True, changes=changes)
    targets = tuple(_code(part.strip(), lineno) for part in core.split(","))
    return MappingRow(_code(upstream, lineno), targets, dropped=False, changes=changes)


def parse_attributions(text: str) -> Attributions:
    """Parse the ATTRIBUTIONS.md mapping format; a malformed row raises ``ValueError``."""
    parsed = Attributions()
    source: Source | None = None
    skill: str | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            heading = line[3:].strip()
            source = None if heading == ENGINE_WRITTEN_HEADING else Source(heading)
            if source is not None:
                parsed.sources[heading] = source
            skill = None
        elif line.startswith("### "):
            skill = line[4:].strip()
            if source is not None:
                source.skills.setdefault(skill, SkillMapping())
            else:
                parsed.engine_written.setdefault(skill, [])
        elif (commit := _COMMIT_RE.match(line)) and source is not None:
            source.commit = commit.group(1)
        elif line.startswith("|") and source is not None and skill is not None:
            cells = _row_cells(line)
            if tuple(cells) == _TABLE_HEADER or set("".join(cells)) <= {"-", " "}:
                continue
            source.skills[skill].rows.append(_parse_row(line, lineno))
        elif (bullet := _BULLET_RE.match(line)) and skill is not None:
            if source is not None:
                source.skills[skill].distilled.append(bullet.group(1))
            else:
                parsed.engine_written[skill].append(bullet.group(1))
    return parsed


def load_core_attributions() -> Attributions:
    """The shipped ``catalog/core/ATTRIBUTIONS.md``, parsed."""
    return parse_attributions(ATTRIBUTIONS_PATH.read_text(encoding="utf-8"))


def _skill_files(skill_dir: Path, sources: Mapping[str, str]) -> set[str]:
    """Every file of ``skill_dir`` (POSIX, relative), license copies and tool caches aside."""
    licenses = {f"{LICENSE_DIR}/{license_name(source)}" for source in sources}
    files = set()
    for path in skill_dir.rglob("*"):
        parts = path.relative_to(skill_dir).parts
        if not path.is_file() or any(p.startswith(".") or p == "__pycache__" for p in parts):
            continue
        files.add("/".join(parts))
    return files - licenses


def _covers(listed: str, rel: str) -> bool:
    """True when the listed core path is ``rel`` or, ending in ``/``, a directory above it."""
    return rel.startswith(listed) if listed.endswith("/") else rel == listed


def _exists(skill_dir: Path, listed: str) -> bool:
    path = skill_dir / listed
    return path.is_dir() if listed.endswith("/") else path.is_file()


def _pin_errors(parsed: Attributions, pins: Mapping[str, str]) -> list[str]:
    errors = [
        f"{name}: no section for this pinned source" for name in pins if name not in parsed.sources
    ]
    for name, source in parsed.sources.items():
        if name not in pins:
            errors.append(f"{name}: a source without a D11 pin")
        elif source.commit != pins[name]:
            errors.append(f"{name}: commit {source.commit} does not match the D11 pin {pins[name]}")
    return errors


def _row_errors(parsed: Attributions) -> list[str]:
    errors = []
    for name, source in parsed.sources.items():
        seen: set[str] = set()
        for skill, mapping in source.skills.items():
            for row in mapping.rows:
                if row.upstream in seen:
                    errors.append(f"{name}: `{row.upstream}` appears in more than one row")
                seen.add(row.upstream)
                if not row.changes:
                    missing = "is dropped without a reason" if row.dropped else "lists no changes"
                    errors.append(f"{name}/{skill}: `{row.upstream}` {missing}")
    return errors


def _mappings(parsed: Attributions, skill: str) -> list[SkillMapping]:
    """Every source's sub-section for ``skill``."""
    return [source.skills[skill] for source in parsed.sources.values() if skill in source.skills]


def _coverage_errors(
    parsed: Attributions, skills_root: Path, sources: Mapping[str, str]
) -> list[str]:
    on_disk = {p.name for p in skills_root.iterdir() if p.is_dir()}
    listed_skills = set(parsed.engine_written).union(
        *(source.skills for source in parsed.sources.values())
    )
    errors = []
    for skill in sorted(on_disk | listed_skills):
        skill_dir = skills_root / skill
        mappings = _mappings(parsed, skill)
        vendored = {t for m in mappings for row in m.rows for t in row.targets}
        vendored |= {path for m in mappings for path in m.distilled}
        engine = set(parsed.engine_written.get(skill, []))
        errors += [
            f"{skill}/{listed}: listed in ATTRIBUTIONS.md but not in the skill"
            for listed in sorted(vendored | engine)
            if not _exists(skill_dir, listed)
        ]
        errors += [
            f"{skill}/{listed}: listed as engine-written and as holding upstream text"
            for listed in sorted(engine & vendored)
        ]
        files = _skill_files(skill_dir, sources) if skill_dir.is_dir() else set()
        errors += [
            f"{skill}/{rel}: neither a mapping target nor engine-written in ATTRIBUTIONS.md"
            for rel in sorted(files)
            if not any(_covers(listed, rel) for listed in vendored | engine)
        ]
    return errors


def _license_errors(
    parsed: Attributions, skills_root: Path, license_sha256: Mapping[str, str]
) -> list[str]:
    errors = []
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        skill = skill_dir.name
        for source, sha256 in license_sha256.items():
            name = f"{LICENSE_DIR}/{license_name(source)}"
            mapping = parsed.sources[source].skills.get(skill) if source in parsed.sources else None
            has_text = mapping is not None and any(not row.dropped for row in mapping.rows)
            copy = skill_dir / name
            if has_text and not copy.is_file():
                errors.append(f"{skill}: holds text from {source} but ships no {name}")
            elif copy.is_file() and not has_text:
                errors.append(f"{skill}: ships {name} but holds no text from {source}")
            if copy.is_file() and hashlib.sha256(copy.read_bytes()).hexdigest() != sha256:
                errors.append(f"{skill}/{name}: not byte-identical to {source}'s license")
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
        in_place = (
            len(rel.parts) == 4
            and rel.parts[0] == CORE_SKILLS_ROOT.name
            and rel.parts[2] == LICENSE_DIR
            and rel.name == license_name(source)
        )
        if not in_place:
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
    license_sha256: Mapping[str, str] = LICENSE_SHA256,
) -> list[str]:
    """Every D31 violation of ``parsed`` against the core skill tree at ``skills_root``.

    Pins equal D11; every skill file (license copies aside) is a mapping target,
    distilled or engine-written, and every listed file exists; no file is both
    engine-written and vendored; an upstream file appears in at most one row per
    source; every row says what changed or, for DROP, why; a skill holding a
    source's text ships that source's byte-identical license copy, and no copy
    ships without that text. ``[]`` means the map is complete.
    """
    return (
        _pin_errors(parsed, pins)
        + _row_errors(parsed)
        + _coverage_errors(parsed, skills_root, license_sha256)
        + _license_errors(parsed, skills_root, license_sha256)
    )
