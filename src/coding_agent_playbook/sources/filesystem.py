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

from coding_agent_playbook.config import Config
from coding_agent_playbook.lockfile import Lockfile
from coding_agent_playbook.sources.base import ArtifactSource, StateSource
from coding_agent_playbook.types import Rule

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coding_agent_playbook.types import Prompt, Skill

# Placeholder for eval tasks until PR 11 defines the type. Listed by ID only
# for now so that list_eval_tasks() can return an empty list without raising.
EvalTask = Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` on top of ``base``.

    Override wins on scalars/lists; nested dicts merge key-by-key. Used to
    let ``.coding-agent-playbook.local.toml`` layer over the committed
    ``.coding-agent-playbook.toml`` per SPEC §7.2.
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
    lists of those. Reject anything else with TypeError so future Config-shape
    changes fail loudly rather than silently producing invalid TOML.
    """
    # bool must come before int — `isinstance(True, int)` is True in Python.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        # tomllib treats \, " and control chars specially in basic strings.
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_scalar(item) for item in value) + "]"
    raise TypeError(f"_dump_toml does not support value of type {type(value).__name__}: {value!r}")


def _dump_toml(data: dict[str, Any]) -> str:
    """Serialize ``data`` to a TOML document.

    Only handles the shapes produced by ``Config.to_dict()`` and
    ``Lockfile.to_dict()``: top-level scalars/lists, single-level mappings
    used as ``[section]`` headers, and a single list-of-tables case used for
    lockfile entries.
    """
    lines: list[str] = []
    section_keys: list[str] = []
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
            if lines:
                lines.append("")
            lines.append(f"[{key}]")
            for subkey, subvalue in value.items():
                if isinstance(subvalue, dict):
                    raise TypeError(
                        f"_dump_toml supports only single-level mappings; nested mapping "
                        f"at [{key}].{subkey}"
                    )
                lines.append(f"{subkey} = {_format_toml_scalar(subvalue)}")
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
    # ``Traversable`` doesn't expose .is_dir on every backend, but the on-disk
    # MultiplexedPath/PosixPath used in v1 does. Stringify and check.
    candidate = Path(str(resource_root))
    if not candidate.is_dir():
        return None
    return candidate


def _iter_md_files(root: Path) -> Iterator[Path]:
    """Yield ``*.md`` and ``*.md.j2`` files under ``root`` in deterministic order."""
    for path in sorted(root.rglob("*.md*")):
        if path.name.endswith(".md") or path.name.endswith(".md.j2"):
            yield path


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

    def list_rules(self) -> list[Rule]:
        rules: list[Rule] = []
        rules.extend(self._walk_rules(self._engine_package))
        for pkg in self._overlay_packages:
            rules.extend(self._walk_rules(pkg))
        playbook_rules = self._repo_root / "playbook" / "rules"
        if playbook_rules.is_dir():
            for md in _iter_md_files(playbook_rules):
                rules.append(Rule.from_markdown(md, "<repo-local>"))
        return rules

    def list_prompts(self) -> list[Prompt]:
        raise NotImplementedError("list_prompts lands in Task C.7")

    def list_skills(self) -> list[Skill]:
        raise NotImplementedError("list_skills lands in Task C.7")

    def _walk_rules(self, package: str) -> list[Rule]:
        rules: list[Rule] = []
        root = _resource_subdir(package, "rules")
        if root is None:
            return rules
        for md in _iter_md_files(root):
            rules.append(Rule.from_markdown(md, package))
        return rules

    def list_eval_tasks(self) -> list[EvalTask]:
        # PR 11 populates this with real EvalTask objects.
        return []


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
            raise FileNotFoundError(f"missing {primary.name}; run `cap init`")
        with primary.open("rb") as f:
            data = tomllib.load(f)
        local = self._repo_root / self._CONFIG_LOCAL_FILENAME
        if local.is_file():
            with local.open("rb") as f:
                local_data = tomllib.load(f)
            data = _deep_merge(data, local_data)
        return Config.from_dict(data)

    def save_config(self, config: Config) -> None:
        target = self._repo_root / self._CONFIG_FILENAME
        target.write_text(_dump_toml(config.to_dict()), encoding="utf-8")

    def load_lockfile(self) -> Lockfile | None:
        target = self._repo_root / self._LOCKFILE_FILENAME
        if not target.is_file():
            return None
        with target.open("rb") as f:
            data = tomllib.load(f)
        return Lockfile.from_dict(data)

    def save_lockfile(self, lockfile: Lockfile) -> None:
        target = self._repo_root / self._LOCKFILE_FILENAME
        target.write_text(_dump_toml(lockfile.to_dict()), encoding="utf-8")
