"""Filesystem-backed ArtifactSource and StateSource (SPEC §20.3).

These are the v1 implementations. They depend only on stdlib (tomllib,
pathlib, importlib.resources, importlib.metadata) plus pyyaml for the
frontmatter helpers already in types.py.
"""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coding_agent_playbook import _toml
from coding_agent_playbook.config import Config
from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.lockfile import Lockfile
from coding_agent_playbook.sources.base import ArtifactSource, StateSource
from coding_agent_playbook.types import Prompt, Rule, Skill, split_frontmatter

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import TypeVar

    from coding_agent_playbook.evals.task import EvalTask

    _T = TypeVar("_T")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` on top of ``base``.

    Override wins on scalars/lists; nested dicts merge key-by-key. Used to
    let ``.coding-agent-playbook.local.toml`` layer over the committed
    ``.coding-agent-playbook.toml`` per SPEC §7.2.

    On type mismatch (one side dict, the other a scalar/list), override
    wins silently — there is no warning. This means a typo'd ``.local.toml``
    that turns ``[user_choices]`` from a table into a scalar will overwrite
    the entire section. Acceptable for v1; a future ``playbook validate`` pass
    should flag suspicious overrides.
    """
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _format_toml_scalar(value: Any) -> str:
    """Render a scalar Python value as a TOML literal.

    Supports the value shapes Config/Lockfile produce: str, bool, int, and
    lists of those. Dicts are *not* supported here (the flat Config/Lockfile
    layout never nests scalars); they fall through to ``TypeError`` like any
    other unsupported type. Delegates to :mod:`coding_agent_playbook._toml` for
    the shared escape ladder, preserving the historical ``_dump_toml …`` error
    wording so callers and tests see no behaviour change.
    """
    return _toml.format_scalar(value, type_error_prefix="_dump_toml")


def _dump_toml(data: dict[str, Any]) -> str:
    """Serialize ``data`` to a TOML document.

    Handles the shapes produced by ``Config.to_dict()`` and
    ``Lockfile.to_dict()``: top-level scalars/lists, single-level mappings
    used as ``[section]`` headers, two-level nested mappings emitted as
    ``[parent.child]`` dotted-table headers (e.g. ``detector_cache.frameworks``
    per SPEC §8.2), and a single list-of-tables case used for lockfile
    entries. Mappings nested deeper than two levels raise ``TypeError``.
    """
    lines: list[str] = []
    section_keys: list[str] = []
    # Emit scalars before section headers — TOML requires top-level keys to
    # appear above any [section] headers, otherwise the parser puts them
    # under the previous section.
    for key, value in data.items():
        if isinstance(value, dict):
            section_keys.append(key)
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            # Reserve list-of-tables for the lockfile entries case.
            section_keys.append(key)
        else:
            lines.append(f"{key} = {_format_toml_scalar(value)}")

    for key in section_keys:
        value = data[key]
        if isinstance(value, dict):
            _emit_table(lines, [key], value)
        else:
            # list-of-tables — TOML [[key]] syntax
            for entry in value:
                if lines:
                    lines.append("")
                lines.append(f"[[{key}]]")
                for subkey, subvalue in entry.items():
                    if isinstance(subvalue, dict):
                        raise TypeError(
                            f"_dump_toml supports only single-level mappings; nested mapping "
                            f"at [[{key}]].{subkey}"
                        )
                    lines.append(f"{subkey} = {_format_toml_scalar(subvalue)}")
    return "\n".join(lines) + "\n"


def _emit_table(lines: list[str], path: list[str], table: dict[str, Any]) -> None:
    """Emit a TOML ``[a.b]`` table header plus its scalar children, then
    recurse into any dict-valued children as ``[a.b.subkey]`` sub-tables.

    Only two levels of nesting are allowed: a top-level ``[section]`` plus at
    most one nested ``[section.child]``. Inside a ``[section.child]`` table,
    encountering another dict value raises ``TypeError`` because Config/Lockfile
    don't need deeper structure, and a deeper schema should fail loudly rather
    than silently produce ambiguous TOML.
    """
    if lines:
        lines.append("")
    lines.append(f"[{'.'.join(path)}]")
    nested: list[tuple[str, dict[str, Any]]] = []
    for subkey, subvalue in table.items():
        if isinstance(subvalue, dict):
            if len(path) >= 2:
                raise TypeError(
                    f"_dump_toml supports at most 2-level nested mappings; nested mapping "
                    f"at [{'.'.join([*path, subkey])}]"
                )
            nested.append((subkey, subvalue))
        else:
            lines.append(f"{subkey} = {_format_toml_scalar(subvalue)}")
    for subkey, subtable in nested:
        _emit_table(lines, [*path, subkey], subtable)


def _resource_subdir(package: str, subdir: str) -> Path | None:
    """Resolve ``<package>/resources/<subdir>`` via importlib.resources.

    Returns ``None`` if the package is not importable, has no ``resources/``
    directory, or has no matching subdirectory. Never raises — sources should
    silently skip packages that ship no artifacts of a given kind (SPEC §20.3).
    """
    try:
        resource_root = resources.files(package).joinpath("resources", subdir)
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    # We need a ``Path`` for ``rglob``-based walking, not just a
    # ``Traversable``. The on-disk backend used by
    # ``resources.files(<importable-package>)`` always materializes as a
    # ``PosixPath``/``MultiplexedPath``, so ``Path(str(...))`` is safe.
    candidate = Path(str(resource_root))
    if not candidate.is_dir():
        return None
    return candidate


def _iter_md_files(root: Path) -> Iterator[Path]:
    """Yield ``*.md`` and ``*.md.j2`` files under ``root`` in deterministic order."""
    for path in sorted(root.rglob("*.md*")):
        # Skip dotted directories (.git, .venv, node_modules-of-vendored-skills,
        # etc.) for hygiene — these never legitimately contain canonical
        # artifacts, and walking them silently inflates source listings.
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        # Note: case-sensitive on Linux/macOS APFS (lowercase .md convention).
        # Banking deployments on case-insensitive volumes may need to revisit.
        if path.name.endswith(".md") or path.name.endswith(".md.j2"):
            yield path


def _iter_skills(skills_root: Path, source_package: str) -> Iterator[Skill]:
    """Yield one ``Skill`` per subdirectory of ``skills_root`` (SPEC §6.3.1).

    Each skill directory must contain ``SKILL.md`` (or ``SKILL.md.j2``).
    ``scripts/`` and ``references/`` sibling subdirectories are recorded on
    the Skill if present.
    """
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        skill_md = _find_skill_md(skill_dir)
        if skill_md is None:
            continue
        text = skill_md.read_text(encoding="utf-8")
        frontmatter, body = split_frontmatter(text)
        scripts_dir = skill_dir / "scripts"
        references_dir = skill_dir / "references"
        yield Skill(
            frontmatter=frontmatter,
            body=body,
            scripts_dir=scripts_dir if scripts_dir.is_dir() else None,
            references_dir=references_dir if references_dir.is_dir() else None,
            source_package=source_package,
        )


def _atomic_write_text(target: Path, content: str) -> None:
    """Write ``content`` to ``target`` atomically.

    Writes to ``target + ".tmp"`` first, then renames over the target. A SIGKILL
    or power loss mid-write leaves either the old file intact or the new file
    fully written — never a half-written one. Used for both
    ``.coding-agent-playbook.toml`` and ``.coding-agent-playbook.lock`` so a
    crashed ``playbook sync`` can be safely retried.
    """
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)


def _find_skill_md(skill_dir: Path) -> Path | None:
    """Return ``SKILL.md`` or ``SKILL.md.j2`` inside ``skill_dir`` if it exists."""
    for candidate_name in ("SKILL.md", "SKILL.md.j2"):
        candidate = skill_dir / candidate_name
        if candidate.is_file():
            return candidate
    return None


class FileSystemArtifactSource(ArtifactSource):
    """Walks importlib.resources for the engine + overlay packages, plus
    <repo>/playbook/ for repo-local artifacts (SPEC §20.3, §11)."""

    name = "filesystem"

    def __init__(
        self,
        *,
        repo_root: Path,
        engine_package: str = "coding_agent_playbook",
        overlay_packages: list[str] | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._engine_package = engine_package
        self._overlay_packages = overlay_packages or []

    @property
    def engine_package(self) -> str:
        """Public read-only accessor for the engine package name.

        Callers that need to walk the same package set this source walks
        (e.g. ``commands/validate.py``'s per-task loader-error aggregator)
        should use this and :attr:`overlay_packages` instead of reaching
        into the private ``_engine_package`` / ``_overlay_packages``
        attributes, so a future rename can't silently degrade them.
        """
        return self._engine_package

    @property
    def overlay_packages(self) -> tuple[str, ...]:
        """Public read-only accessor for the overlay package names.

        Returns a tuple (not the live list) so callers cannot mutate the
        source's internal package list. Order matches the walk order in
        :meth:`list_rules` / :meth:`list_prompts` / :meth:`list_eval_tasks`.
        """
        return tuple(self._overlay_packages)

    def list_rules(self) -> list[Rule]:
        return self._walk_artifacts(
            subdir="rules",
            builder=Rule.from_markdown,
        )

    def list_prompts(self) -> list[Prompt]:
        return self._walk_artifacts(
            subdir="prompts",
            builder=Prompt.from_markdown,
        )

    def list_skills(self) -> list[Skill]:
        skills: list[Skill] = []
        for package in (self._engine_package, *self._overlay_packages):
            root = _resource_subdir(package, "skills")
            if root is None:
                continue
            skills.extend(_iter_skills(root, package))
        repo_local_root = self._repo_root / "playbook" / "skills"
        if repo_local_root.is_dir():
            skills.extend(_iter_skills(repo_local_root, "<repo-local>"))
        return skills

    def _walk_artifacts(
        self,
        *,
        subdir: str,
        builder: Callable[[Path, str], _T],
    ) -> list[_T]:
        items: list[_T] = []
        for package in (self._engine_package, *self._overlay_packages):
            root = _resource_subdir(package, subdir)
            if root is None:
                continue
            for md in _iter_md_files(root):
                items.append(builder(md, package))
        repo_local_root = self._repo_root / "playbook" / subdir
        if repo_local_root.is_dir():
            for md in _iter_md_files(repo_local_root):
                items.append(builder(md, "<repo-local>"))
        return items

    def list_eval_tasks(self) -> list[EvalTask]:
        """Walk engine + overlay packages + repo-local for ``eval_tasks/<id>/``.

        Mirrors the rules/prompts walking pattern: each layer's
        ``resources/eval_tasks/`` is scanned via :func:`_resource_subdir`, then
        ``<repo>/playbook/eval_tasks/`` is appended. Later layers do NOT
        override earlier ones here — the orchestrator's :class:`OverlayResolver`
        handles ID-based collision semantics for rules/prompts/skills, but eval
        tasks are aggregated as-is in v1 (no per-layer override pass yet; the
        collision-by-id pattern is identical and lands when first overlay
        ships eval tasks). All entries are returned with their ``source_package``
        set to the importable package name or ``"<repo-local>"``.
        """
        tasks: list[EvalTask] = []
        for package in (self._engine_package, *self._overlay_packages):
            root = _resource_subdir(package, "eval_tasks")
            if root is None:
                continue
            for task_dir in discover_eval_task_dirs(root):
                tasks.append(load_eval_task_from_dir(task_dir, source_package=package))
        repo_local = self._repo_root / "playbook" / "eval_tasks"
        for task_dir in discover_eval_task_dirs(repo_local):
            tasks.append(load_eval_task_from_dir(task_dir, source_package="<repo-local>"))
        return tasks


class FileSystemStateSource(StateSource):
    """Reads + writes the three TOML files in the consumer repo:
    .coding-agent-playbook.toml, .coding-agent-playbook.local.toml,
    .coding-agent-playbook.lock (SPEC §7, §14.4, §20.3)."""

    name = "filesystem"

    _CONFIG_FILENAME = ".coding-agent-playbook.toml"
    _CONFIG_LOCAL_FILENAME = ".coding-agent-playbook.local.toml"
    _LOCKFILE_FILENAME = ".coding-agent-playbook.lock"

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = repo_root

    def load_config(self) -> Config:
        primary = self._repo_root / self._CONFIG_FILENAME
        if not primary.is_file():
            raise FileNotFoundError(f"missing {primary.name}; run `playbook init`")
        with primary.open("rb") as f:
            data = tomllib.load(f)
        local = self._repo_root / self._CONFIG_LOCAL_FILENAME
        if local.is_file():
            with local.open("rb") as f:
                local_data = tomllib.load(f)
            data = _deep_merge(data, local_data)
        return Config.from_dict(data)

    def save_config(self, config: Config) -> None:
        _atomic_write_text(
            self._repo_root / self._CONFIG_FILENAME,
            _dump_toml(config.to_dict()),
        )

    def load_lockfile(self) -> Lockfile | None:
        """Read the lockfile. Returns ``None`` if no lockfile exists (= first
        sync, no drift baseline yet). ``playbook sync --check`` treats ``None`` as
        'no comparison possible — emit a baseline'."""
        target = self._repo_root / self._LOCKFILE_FILENAME
        if not target.is_file():
            return None
        with target.open("rb") as f:
            data = tomllib.load(f)
        return Lockfile.from_dict(data)

    def save_lockfile(self, lockfile: Lockfile) -> None:
        _atomic_write_text(
            self._repo_root / self._LOCKFILE_FILENAME,
            _dump_toml(lockfile.to_dict()),
        )
