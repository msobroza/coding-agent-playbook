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
from coding_agent_playbook._atomic_io import atomic_write_bytes
from coding_agent_playbook._layers import ENGINE_PACKAGE as ENGINE_PACKAGE
from coding_agent_playbook._layers import REPO_LOCAL_SOURCE as REPO_LOCAL_SOURCE
from coding_agent_playbook.config import Config, check_enabled_keys
from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.lockfile import Lockfile
from coding_agent_playbook.sources._hook_walk import walk_hook_layer
from coding_agent_playbook.sources.base import ArtifactSource, StateSource
from coding_agent_playbook.types import Prompt, Rule, Skill, split_frontmatter

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from typing import TypeVar

    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.types import Hook, HookSchemaError

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


#: Table-header depth the writer emits (``[detector_cache.frameworks]``, SPEC
#: §8.2). A table nested deeper is an inline table under its parent header, so
#: the engine's own Config/Lockfile shapes serialize exactly as before P6 while
#: any table a user writes in ``extra_tables`` still round-trips.
_MAX_HEADER_DEPTH = 2


def _format_toml_scalar(value: Any) -> str:
    """Render a value as a TOML literal: a scalar, an array or an inline table.

    Delegates to :mod:`coding_agent_playbook._toml` for the shared escape
    ladder, preserving the historical ``_dump_toml …`` error wording. Dicts are
    inline tables (P6): they only reach here below :data:`_MAX_HEADER_DEPTH`,
    inside an array or inside a ``[[x]]`` entry.
    """
    return _toml.format_scalar(value, allow_inline_table=True, type_error_prefix="_dump_toml")


def _dump_toml(data: dict[str, Any]) -> str:
    """Serialize ``data`` to a TOML document.

    Top-level scalars and arrays come first, then each mapping as a
    ``[section]`` (sub-mappings as ``[parent.child]`` headers, deeper ones as
    inline tables, see :func:`_emit_table`) and each non-empty list of mappings
    as ``[[key]]`` entries (the lockfile's ``entries``). Every key and header
    segment goes through :func:`_toml.format_key`, so ``[hooks."a.b"]`` and
    non-ASCII keys parse back.

    Example::

        >>> print(_dump_toml({"v": 1, "a": {"x": 2, "b": {"c": {"d": 0.5}}}}), end="")
        v = 1
        <BLANKLINE>
        [a]
        x = 2
        <BLANKLINE>
        [a.b]
        c = { d = 0.5 }
    """
    lines: list[str] = []
    sections: list[tuple[str, Any]] = []
    # Emit scalars before section headers — TOML requires top-level keys to
    # appear above any [section] headers, otherwise the parser puts them
    # under the previous section.
    for key, value in data.items():
        if isinstance(value, dict) or _is_array_of_tables(value):
            sections.append((key, value))
        else:
            lines.append(_key_value_line(key, value))
    for key, value in sections:
        if isinstance(value, dict):
            _emit_table(lines, [key], value)
        else:
            _emit_array_of_tables(lines, key, value)
    return "\n".join(lines) + "\n"


def _is_array_of_tables(value: object) -> bool:
    """True for a non-empty list whose every item is a mapping (``[[key]]`` form)."""
    return isinstance(value, list) and bool(value) and all(isinstance(v, dict) for v in value)


def _key_value_line(key: str, value: Any) -> str:
    """``key = value`` with the key quoted when it is not a bare TOML key."""
    return f"{_toml.format_key(key)} = {_format_toml_scalar(value)}"


def _emit_array_of_tables(lines: list[str], key: str, entries: list[dict[str, Any]]) -> None:
    """Emit one ``[[key]]`` table per entry; nested values are inline."""
    for entry in entries:
        if lines:
            lines.append("")
        lines.append(f"[[{_toml.format_key(key)}]]")
        lines.extend(_key_value_line(subkey, subvalue) for subkey, subvalue in entry.items())


def _emit_table(lines: list[str], path: list[str], table: dict[str, Any]) -> None:
    """Emit a TOML ``[a.b]`` table header plus its key/value lines, then
    recurse into any dict-valued children as ``[a.b.subkey]`` sub-tables.

    Headers go at most :data:`_MAX_HEADER_DEPTH` levels deep: inside a
    ``[section.child]`` table a dict value is written as an inline table on its
    key's line, never as an error (P6 — a preserved ``[metrics.thresholds]``
    holds one table per metric).
    """
    if lines:
        lines.append("")
    lines.append(f"[{'.'.join(_toml.format_key(part) for part in path)}]")
    nested: list[tuple[str, dict[str, Any]]] = []
    for subkey, subvalue in table.items():
        if isinstance(subvalue, dict) and len(path) < _MAX_HEADER_DEPTH:
            nested.append((subkey, subvalue))
        else:
            lines.append(_key_value_line(subkey, subvalue))
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
    except Exception:
        # ``files()`` imports the package, and an overlay's import may raise
        # anything (its own code, a missing dependency, an empty name). Skip it
        # like a missing one: sync/validate/check/init run the shared
        # ``_sync_preflight.unusable_overlays`` check, which names it and the
        # error, so discovery must not crash before that check can report it.
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
    """Write ``content`` to ``target`` atomically, as UTF-8 bytes.

    A SIGKILL or power loss mid-write leaves either the old file intact or the
    new file fully written — never a half-written one. Used for both
    ``.coding-agent-playbook.toml`` and ``.coding-agent-playbook.lock`` so a
    crashed ``playbook sync`` can be safely retried. It delegates to the byte
    writer because ``Path.write_text`` translates ``\\n`` on Windows.
    """
    atomic_write_bytes(target, content.encode("utf-8"))


def _read_config_file(path: Path) -> dict[str, Any]:
    """Parse one config file, refusing enabled-list shapes ``Config`` would misread.

    Each file is checked on its own, before the SPEC §7.2 deep merge, so a
    :class:`~coding_agent_playbook.config.ConfigError` names the file that holds
    the mistake (``.coding-agent-playbook.local.toml: the [adapters] table …``).
    """
    with path.open("rb") as f:
        data = tomllib.load(f)
    check_enabled_keys(data, source=path.name)
    return data


def _find_skill_md(skill_dir: Path) -> Path | None:
    """Return ``SKILL.md`` or ``SKILL.md.j2`` inside ``skill_dir`` if it exists."""
    for candidate_name in ("SKILL.md", "SKILL.md.j2"):
        candidate = skill_dir / candidate_name
        if candidate.is_file():
            return candidate
    return None


class FileSystemArtifactSource(ArtifactSource):
    """Walks importlib.resources for the engine + overlay packages, plus
    <repo>/playbook/ for repo-local artifacts (SPEC §20.3, §11).

    ``extra_resource_roots`` adds ``resources/`` directories found by path
    rather than by package name — config-less ``playbook validate`` passes an
    overlay checkout's ``<root>/src/<pkg>/resources/`` (prK §P P8). Every
    walker, and validate's per-layer checks, go through :meth:`layer_roots`.
    """

    name = "filesystem"

    def __init__(
        self,
        *,
        repo_root: Path,
        engine_package: str = ENGINE_PACKAGE,
        overlay_packages: list[str] | None = None,
        extra_resource_roots: Sequence[Path] = (),
    ) -> None:
        self._repo_root = repo_root
        self._engine_package = engine_package
        self._overlay_packages = overlay_packages or []
        self._extra_resource_roots = tuple(extra_resource_roots)

    @property
    def engine_package(self) -> str:
        """Public read-only accessor for the engine package name.

        Callers that need to walk the same package set this source walks
        should prefer :meth:`layer_roots`; this and :attr:`overlay_packages`
        stay public so nobody reaches into the private ``_engine_package`` /
        ``_overlay_packages`` attributes, which a rename would silently degrade.
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

    @property
    def extra_resource_roots(self) -> tuple[Path, ...]:
        """The path-based ``resources/`` layers, walked after the overlays."""
        return self._extra_resource_roots

    def layer_roots(self, subdir: str) -> list[tuple[str, Path]]:
        """``(source_package, <layer>/<subdir>)`` for each layer that has ``subdir``.

        Layers come in resolution order (later wins, SPEC §11): the engine
        package, the overlays in ``overlays_enabled`` order, the extra
        ``resources/`` roots, then repo-local ``playbook/``. The label is what
        artifacts found there carry as ``source_package``: the package name,
        the extra root's parent directory name, or ``"<repo-local>"``. A
        layer's containment root for links is ``root.parent``.

        Example::

            >>> FileSystemArtifactSource(repo_root=Path("/repo")).layer_roots("rules")[0][0]
            'coding_agent_playbook'
        """
        candidates: list[tuple[str, Path | None]] = [
            *((package, _resource_subdir(package, subdir)) for package in self._packages()),
            *((root.parent.name, root / subdir) for root in self._extra_resource_roots),
            (REPO_LOCAL_SOURCE, self._repo_root / "playbook" / subdir),
        ]
        return [(label, root) for label, root in candidates if root is not None and root.is_dir()]

    def _packages(self) -> tuple[str, ...]:
        """The importable layers: the engine package, then the overlays."""
        return (self._engine_package, *self._overlay_packages)

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
        return [
            skill
            for label, root in self.layer_roots("skills")
            for skill in _iter_skills(root, label)
        ]

    def list_hooks(self) -> list[Hook]:
        """Every hook directory of every layer, in :meth:`layer_roots` order (prK §A.5).

        Fails loudly, like ``Rule.from_markdown``: raises the first
        :class:`~coding_agent_playbook.types.HookSchemaError` that
        :meth:`collect_hooks` finds.
        """
        hooks, errors = self.collect_hooks()
        if errors:
            raise errors[0]
        return hooks

    def collect_hooks(self) -> tuple[list[Hook], list[HookSchemaError]]:
        """Every well-formed hook plus every malformed one's error, never raising.

        What ``SyncContext.from_repo(..., tolerate_hook_errors=True)`` reads, so
        ``playbook validate`` reports each malformed hook (prK §P P8c).

        Example::

            >>> FileSystemArtifactSource(repo_root=Path("/no/such/repo")).collect_hooks()
            ([], [])
        """
        walks = [walk_hook_layer(root, label) for label, root in self.layer_roots("hooks")]
        return [h for walk in walks for h in walk.hooks], [e for walk in walks for e in walk.errors]

    def _walk_artifacts(
        self,
        *,
        subdir: str,
        builder: Callable[[Path, str], _T],
    ) -> list[_T]:
        return [
            builder(md, label)
            for label, root in self.layer_roots(subdir)
            for md in _iter_md_files(root)
        ]

    def list_eval_tasks(self) -> list[EvalTask]:
        """Walk every layer's ``eval_tasks/<id>/`` (:meth:`layer_roots` order).

        Later layers do NOT override earlier ones here — the orchestrator's
        :class:`OverlayResolver` handles ID-based collision semantics for
        rules/prompts/skills, but eval tasks are aggregated as-is in v1 (no
        per-layer override pass yet; the collision-by-id pattern is identical
        and lands when first overlay ships eval tasks). Each task's
        ``source_package`` is its layer's label.
        """
        return [
            load_eval_task_from_dir(task_dir, source_package=label)
            for label, root in self.layer_roots("eval_tasks")
            for task_dir in discover_eval_task_dirs(root)
        ]


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
        """Read the committed config with the local overrides merged on top (SPEC §7.2).

        Raises :class:`FileNotFoundError` without the committed file and
        :class:`~coding_agent_playbook.config.ConfigError` (naming the file) for
        a shape ``Config`` would misread — before anything else runs.
        """
        primary = self._primary_config_path()
        data = _deep_merge(_read_config_file(primary), self.load_local_overrides())
        return Config.from_dict(data, source=primary.name)

    def load_primary_config(self) -> Config:
        """Read the committed config alone, never merging ``.local.toml`` (P6).

        What ``playbook init`` and ``playbook check --refresh`` modify and save:
        the merged view would bake personal overrides into the committed file.
        Raises like :meth:`load_config` for a missing or misread committed file.

        Example::

            >>> FileSystemStateSource(repo_root=Path("/no/such/repo")).load_primary_config()
            Traceback (most recent call last):
            ...
            FileNotFoundError: missing .coding-agent-playbook.toml; run `playbook init`
        """
        primary = self._primary_config_path()
        return Config.from_dict(_read_config_file(primary), source=primary.name)

    def _primary_config_path(self) -> Path:
        """The committed config's path; :class:`FileNotFoundError` when it is absent."""
        primary = self._repo_root / self._CONFIG_FILENAME
        if not primary.is_file():
            raise FileNotFoundError(f"missing {primary.name}; run `playbook init`")
        return primary

    def load_local_overrides(self) -> dict[str, Any]:
        """The checked ``.coding-agent-playbook.local.toml`` table, ``{}`` when absent.

        ``playbook init`` calls it before writing anything, since it writes a
        fresh committed config without loading one.

        Example::

            >>> FileSystemStateSource(repo_root=Path("/no/such/repo")).load_local_overrides()
            {}
        """
        local = self._repo_root / self._CONFIG_LOCAL_FILENAME
        return _read_config_file(local) if local.is_file() else {}

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
