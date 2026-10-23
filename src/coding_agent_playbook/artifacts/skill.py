"""The Skill artifact: a skill directory and its member references (SPEC.md §6.3, §6.6.2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Final, Literal, TypedDict

# Imported at run time: Skill.from_dict rebuilds member references from dicts.
from coding_agent_playbook.artifacts.member_reference import MemberReference
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The name of one byte-copied skill subtree (SPEC §6.3, prU D48).
type SideDirName = Literal["scripts", "references", "examples"]
#: Every side dir name, in write order.
SIDE_DIR_NAMES: Final[tuple[SideDirName, ...]] = ("scripts", "references", "examples")


class SideDirs(TypedDict):
    """A skill directory's side dirs as :class:`Skill` keyword arguments (``None`` when absent)."""

    scripts_dir: Path | None
    references_dir: Path | None
    examples_dir: Path | None


def side_dirs_at(skill_dir: Path) -> SideDirs:
    """The side dirs present in ``skill_dir``, to pass as ``Skill(..., **side_dirs_at(skill_dir))``.

    Example: for a dir holding only ``scripts/`` -> ``{"scripts_dir": skill_dir / "scripts",
    "references_dir": None, "examples_dir": None}``.
    """
    present = {name: skill_dir / name for name in SIDE_DIR_NAMES if (skill_dir / name).is_dir()}
    return SideDirs(
        scripts_dir=present.get("scripts"),
        references_dir=present.get("references"),
        examples_dir=present.get("examples"),
    )


@dataclass(frozen=True)
class ListedReference:
    """One ``playbook.references`` entry whose gate passed, listed by its skill (prU D47).

    ``path`` is relative to the skill directory (``references/<file>`` or
    ``examples/<file-or-dir>``); ``open_when`` is the one-line condition.

    Example: ``ListedReference("references/guide.md", "Choosing a fake.")``.
    """

    path: str
    open_when: str

    def to_dict(self) -> dict[str, str]:
        """Lossless dict form, the inverse of :meth:`from_dict`.

        Example: ``ListedReference("references/a.md", "X.").to_dict()`` ->
        ``{"path": "references/a.md", "open_when": "X."}``.
        """
        return {"path": self.path, "open_when": self.open_when}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ListedReference:
        """Inverse of :meth:`to_dict`: ``ListedReference.from_dict(r.to_dict()) == r``."""
        return cls(path=data["path"], open_when=data["open_when"])


@dataclass
class Skill:
    """A skill directory (SPEC §6.3): ``SKILL.md`` + optional ``scripts/``,
    ``references/`` and ``examples/`` (prU D48). Written natively (Agent Skills layout) by the
    ``claude_code`` / ``opencode`` / ``shared_skills`` adapters through the shared
    ``SkillWriter``; other adapters degrade it via :meth:`to_prompt`.
    ``member_references`` are the skill's active member rules, rendered (ADR 0001)."""

    frontmatter: dict[str, Any]
    body: str
    scripts_dir: Path | None
    references_dir: Path | None
    source_package: str
    # Set by compose_skills at sync: the active member rules, rendered.
    member_references: tuple[MemberReference, ...] = ()
    # The skill's source directory, when it was loaded from one: ``playbook
    # validate`` lists its references/ and examples/ files against
    # ``playbook.references`` (prU D47). None for a skill built in memory.
    source_dir: Path | None = None
    # Set by compose_skills at sync: the playbook.references entries whose
    # applies_if passed, listed under "References and examples" (prU D47).
    listed_references: tuple[ListedReference, ...] = ()
    # The skill's examples/ directory, byte-copied like scripts/ and references/ (prU D48).
    examples_dir: Path | None = None
    # Set by compose_skills at sync: the paths of the playbook.references entries
    # whose applies_if failed; their files are neither listed nor written (D48, D58).
    withheld_paths: tuple[str, ...] = ()

    def side_dir(self, name: SideDirName) -> Path | None:
        """The source dir of side dir ``name``; ``None`` when the skill has none.

        Raises ``ValueError`` naming ``name`` and the allowed names for any other value.

        Example: ``skill.side_dir("examples")`` -> ``skill.examples_dir``.
        """
        dirs: dict[str, Path | None] = {
            "scripts": self.scripts_dir,
            "references": self.references_dir,
            "examples": self.examples_dir,
        }
        if name not in dirs:
            raise ValueError(
                f"unknown skill side dir {name!r}; expected one of {', '.join(SIDE_DIR_NAMES)}"
            )
        return dirs[name]

    def side_dirs(self) -> tuple[tuple[SideDirName, Path | None], ...]:
        """The byte-copied subtrees, ``(name, source dir or None)``, in write order.

        Example: ``dict(skill.side_dirs())["examples"]`` -> ``skill.examples_dir``.
        """
        return tuple((name, self.side_dir(name)) for name in SIDE_DIR_NAMES)

    def side_dir_home(self) -> Path | None:
        """The directory holding the skill's side dirs: the parent of the first one present.

        Example: with ``references_dir=Path("skills/x/references")`` -> ``Path("skills/x")``.
        """
        return next((path.parent for _, path in self.side_dirs() if path is not None), None)

    def is_withheld(self, relative: str) -> bool:
        """Whether sync must not write the file at skill-relative ``relative`` (D48, D58).

        The most specific ``playbook.references`` entry covering the file (its
        own path or a parent directory) decides: a withheld entry withholds it,
        a listed one keeps it; a file no entry covers is written.

        Example: with ``withheld_paths=("examples/app",)``,
        ``skill.is_withheld("examples/app/main.py")`` -> ``True``.
        """
        path = PurePosixPath(relative)
        listed = [(ref.path, False) for ref in self.listed_references]
        withheld = [(entry, True) for entry in self.withheld_paths]
        covering = [
            (len(PurePosixPath(entry).parts), held)
            for entry, held in (*listed, *withheld)
            if path == PurePosixPath(entry) or PurePosixPath(entry) in path.parents
        ]
        # The deepest entry wins. Two entries of one depth name the same path, one
        # listed and one withheld; max() then picks (depth, True), so a failed gate
        # is never overridden by a passing twin.
        return max(covering)[1] if covering else False

    def to_prompt(self) -> Prompt:
        """Degrade this Skill to a Prompt.

        ``scripts_dir`` and ``references_dir`` are intentionally *not* carried
        into the Prompt — adapters that natively support skills (e.g.
        :class:`ClaudeCodeAdapter`) handle those side files separately by
        overriding ``write_skill``. For every other adapter the degrade path
        is lossy by design (SPEC §6.3).

        ``Skill.frontmatter`` is an open ``dict[str, Any]`` because the Claude
        Code SKILL.md schema is not strict YAML the way Rule/Prompt frontmatter
        is. We pull canonical fields out with sensible fallbacks so the
        resulting Prompt is always writable.
        """
        identifier = self.frontmatter.get("id", "skill")
        return Prompt(
            frontmatter=PromptFrontmatter(
                id=identifier,
                name=self.frontmatter.get("name", "Skill"),
                description=self.frontmatter.get("description", ""),
                slash=self.frontmatter.get("slash") or identifier,
            ),
            body=self.body,
            template_body=self.body,
            is_templated=False,
            source_path=None,
            source_package=self.source_package,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dict(self.frontmatter),
            "body": self.body,
            "scripts_dir": None if self.scripts_dir is None else str(self.scripts_dir),
            "references_dir": None if self.references_dir is None else str(self.references_dir),
            "source_package": self.source_package,
            "member_references": [member.to_dict() for member in self.member_references],
            "source_dir": None if self.source_dir is None else str(self.source_dir),
            "listed_references": [ref.to_dict() for ref in self.listed_references],
            "examples_dir": None if self.examples_dir is None else str(self.examples_dir),
            "withheld_paths": list(self.withheld_paths),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        scripts_dir = data["scripts_dir"]
        references_dir = data["references_dir"]
        # A dict written before member references existed has no such key.
        members = data.get("member_references", ())
        source_dir = data.get("source_dir")
        listed = data.get("listed_references", ())
        examples_dir = data.get("examples_dir")
        return cls(
            dict(data["frontmatter"]),
            data["body"],
            None if scripts_dir is None else Path(scripts_dir),
            None if references_dir is None else Path(references_dir),
            data["source_package"],
            tuple(MemberReference.from_dict(member) for member in members),
            None if source_dir is None else Path(source_dir),
            tuple(ListedReference.from_dict(ref) for ref in listed),
            None if examples_dir is None else Path(examples_dir),
            tuple(data.get("withheld_paths", ())),
        )
