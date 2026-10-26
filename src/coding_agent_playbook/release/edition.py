"""The edition loader: a frozen graded set, read closed-world and leniently (#281 ticket 09).

An edition (CONTEXT.md) lives at ``catalog/editions/<tag>/``: its digests file
(``release.edition_digests``) and the frozen prompts and rules under ``core/``.

- **Closed-world**: :func:`load_edition` reads only the files the digests file
  lists, and :meth:`Edition.prompt` resolves a prompt and every rule it includes
  by id inside the edition alone. Nothing comes from the current text, an
  overlay or the local layer, and a missing id is an :class:`EditionError`
  instead of a fallback.
- **Lenient**: frozen files are what an old release shipped, so they may carry
  keys today's loaders refuse (the retired ``version`` and ``eval_samples``, or
  a key a later release drops). The loader keeps only the frontmatter keys
  rendering needs and ignores the rest.

:func:`edition_file_problems` compares the files with the digests file, the
offline check CI runs on every edition.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.release.edition_digests import (
    DIGESTS_FILENAME,
    EditionDigests,
    EditionDigestsError,
    read_edition_digests,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from _typeshed import DataclassInstance

    from coding_agent_playbook.release.edition_digests import EditionArtifact

__all__ = ["Edition", "EditionError", "edition_file_problems", "load_edition"]

#: ``core/skills/<skill>/rules/<file>``: an in-skill rule, a member of ``<skill>``.
_SKILL_RULE_DEPTH: Final = 5


class EditionError(ValueError):
    """An edition that cannot be loaded, or an id it does not hold.

    A ``ValueError``, like the prompt and rule load errors, so the eval prompt
    renderer reports it as an unscorable sample.
    """


@dataclass(frozen=True)
class Edition:
    """One loaded edition: its tag, directory, digests file and frozen artifacts.

    Example::

        >>> load_edition(Path("catalog/editions/v0.1.0")).prompt("review")  # doctest: +SKIP
    """

    tag: str
    root: Path
    digests: EditionDigests
    prompts: Mapping[str, Prompt]
    rules: tuple[Rule, ...]

    def prompt(self, prompt_id: str) -> Prompt:
        """The frozen prompt ``prompt_id``; it and every rule it includes must be in the edition.

        Example::

            >>> edition.prompt("review").frontmatter.id  # doctest: +SKIP
            'review'
        """
        prompt = self.prompts.get(prompt_id)
        if prompt is None:
            raise EditionError(
                f"edition {self.tag} has no prompt {prompt_id!r}; it holds {sorted(self.prompts)}"
            )
        rule_ids = {rule.frontmatter.id for rule in self.rules}
        missing = [rid for rid in prompt.frontmatter.includes_rules if rid not in rule_ids]
        if missing:
            raise EditionError(
                f"edition {self.tag}: prompt {prompt_id!r} includes rules {missing} "
                f"the edition does not hold; it holds {sorted(rule_ids)}"
            )
        return prompt


def load_edition(root: Path) -> Edition:
    """The edition at ``root`` (``catalog/editions/<tag>``), its listed files loaded leniently.

    Raises :class:`EditionError` naming the directory or file at fault.

    Example::

        >>> load_edition(Path("/no/such/edition"))
        Traceback (most recent call last):
        ...
        coding_agent_playbook.release.edition.EditionError: no edition at /no/such/edition ...
    """
    digests_path = root / DIGESTS_FILENAME
    if not digests_path.is_file():
        raise EditionError(f"no edition at {root} (no {DIGESTS_FILENAME}); freeze it first")
    try:
        digests = read_edition_digests(digests_path)
    except EditionDigestsError as exc:
        raise EditionError(str(exc)) from exc
    prompts = {a.id: _lenient_prompt(root, a) for a in digests.artifacts if a.kind == "prompt"}
    rules = tuple(_lenient_rule(root, a) for a in digests.artifacts if a.kind == "rule")
    return Edition(digests.tag, root, digests, prompts, rules)


def _frontmatter(
    path: Path, model: type[DataclassInstance], artifact_id: str
) -> tuple[dict[str, Any], str]:
    """The keys of ``model`` that ``path``'s frontmatter sets, and its body; others are ignored.

    The file's ``id`` must be the one the digests file maps to it.
    """
    try:
        data, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EditionError(f"{path}: cannot read the frozen file: {exc}") from exc
    if data.get("id") != artifact_id:
        raise EditionError(
            f"{path}: frozen file has id {data.get('id')!r}, but {DIGESTS_FILENAME} "
            f"maps id {artifact_id!r} to it"
        )
    known = {field.name for field in dataclasses.fields(model)}
    return {key: value for key, value in data.items() if key in known}, body


def _lenient_prompt(root: Path, artifact: EditionArtifact) -> Prompt:
    path = root / artifact.path
    data, body = _frontmatter(path, PromptFrontmatter, artifact.id)
    try:
        frontmatter = PromptFrontmatter(**data)
    except TypeError as exc:
        raise EditionError(f"{path}: frozen prompt lacks a required key: {exc}") from exc
    return Prompt(frontmatter, body, body, path.name.endswith(".md.j2"), path, ENGINE_PACKAGE)


def _lenient_rule(root: Path, artifact: EditionArtifact) -> Rule:
    path = root / artifact.path
    data, body = _frontmatter(path, RuleFrontmatter, artifact.id)
    home_skill = _home_skill(artifact.path)
    injected = home_skill is not None and data.get("skill") is None
    if injected:
        data["skill"] = home_skill
    try:
        frontmatter = RuleFrontmatter(**data)
    except TypeError as exc:
        raise EditionError(f"{path}: frozen rule lacks a required key: {exc}") from exc
    templated = path.name.endswith(".md.j2")
    return Rule(frontmatter, body, body, templated, path, ENGINE_PACKAGE, home_skill, injected)


def _home_skill(rel: str) -> str | None:
    """``<skill>`` for ``core/skills/<skill>/rules/<file>``, else ``None`` (as the layer walk does)."""
    parts = PurePosixPath(rel).parts
    if len(parts) == _SKILL_RULE_DEPTH and parts[1] == "skills" and parts[3] == "rules":
        return parts[2]
    return None


def edition_file_problems(root: Path) -> list[str]:
    """Why the files under ``root`` do not match its digests file; ``[]`` when they do.

    A listed file that is missing or whose bytes differ, and a file the digests
    file does not list, are each one problem naming the path.

    Example::

        >>> edition_file_problems(Path("catalog/editions/v0.1.0"))  # doctest: +SKIP
        []
    """
    try:
        digests = read_edition_digests(root / DIGESTS_FILENAME)
    except EditionDigestsError as exc:
        return [str(exc)]
    listed = {artifact.path: artifact.sha256 for artifact in digests.artifacts}
    problems = [_listed_problem(root, rel, sha) for rel, sha in sorted(listed.items())]
    problems += [
        f"{root / rel}: not listed in {DIGESTS_FILENAME}; an edition holds only frozen files"
        for rel in _files_under(root)
        if rel not in listed and rel != DIGESTS_FILENAME
    ]
    return [problem for problem in problems if problem]


def _listed_problem(root: Path, rel: str, sha256: str) -> str:
    path = root / rel
    if not path.is_file():
        return f"{path}: missing; {DIGESTS_FILENAME} lists it"
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        return (
            f"{path}: differs from its digest in {DIGESTS_FILENAME}; editions are frozen, "
            "edit the current text under catalog/core/ instead"
        )
    return ""


def _files_under(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
