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

from coding_agent_playbook._toml import dump_toml
from coding_agent_playbook.bundled_content import bundled_layer_root, is_bundled_layer
from coding_agent_playbook.config import Config, ConfigError, check_config_file
from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.lockfile import Lockfile
from coding_agent_playbook.sources.base import ArtifactSource, StateSource
from coding_agent_playbook.types import Prompt, Rule, Skill, split_frontmatter

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from typing import TypeVar

    from coding_agent_playbook.evals.task import EvalTask

    _T = TypeVar("_T")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` on top of ``base``.

    Override wins on scalars/lists; nested dicts merge key-by-key. Used to
    let ``.coding-agent-playbook.local.toml`` layer over the committed
    ``.coding-agent-playbook.toml`` per SPEC §7.2.

    On type mismatch (one side dict, the other a scalar/list), override
    wins silently. For the tables ``Config`` reads that cannot happen: each file
    is checked on its own first (``config.check_config_file``), so a
    ``user_choices = "x"`` in either file is refused, naming that file, before
    any merge. Other unknown keys may still be replaced whole.
    """
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resource_subdir(package: str, subdir: str) -> Path | None:
    """Resolve a layer's ``<subdir>`` kind directory, or ``None`` when it ships none.

    A bundled layer (the engine, or a bundled plugin under either namespace)
    reads ``<subdir>`` from its directory in the content root
    (``bundled_content.bundled_layer_root``) and is never imported. Every other
    package resolves ``<package>/resources/<subdir>`` via importlib.resources.

    Returns ``None`` if the package is not importable, has no ``resources/``
    directory, or has no matching subdirectory, so sources silently skip
    packages that ship no artifacts of a given kind (SPEC §20.3). The one raise
    is :class:`BundledContentMissingError` for a bundled layer when the engine's
    content root is missing: a broken install must fail loudly, not render
    without the engine's artifacts.
    """
    # Outside the ``except Exception`` guard below on purpose: a missing content
    # root must propagate, never read as "this layer ships nothing".
    if is_bundled_layer(package):
        return _bundled_subdir(package, subdir)
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
    # ``Traversable``. On the on-disk backend, ``resources.files(<package>)`` is a
    # ``PosixPath``, or a ``MultiplexedPath`` for a namespace package spread over
    # several portions. ``str()`` of a ``MultiplexedPath`` is not a filesystem
    # path, so the conversion is safe only because it happens after the full
    # two-segment join, which descends into the one portion holding ``<subdir>``.
    # The limit (pre-existing, not supported): a kind directory that itself spans
    # portions stays a ``MultiplexedPath``, ``Path(str(...))`` is not a directory,
    # and that overlay's artifacts of this kind are skipped.
    candidate = Path(str(resource_root))
    if not candidate.is_dir():
        return None
    return candidate


def _bundled_subdir(layer: str, subdir: str) -> Path | None:
    """``<layer root>/<subdir>`` for a bundled layer, or ``None`` when it has no such dir.

    ``layer`` is the engine or a bundled-plugin name (either namespace); an
    unknown plugin leaf resolves to ``None`` like a missing kind directory.
    Raises :class:`BundledContentMissingError` when the content root is missing.

    Example::

        >>> _bundled_subdir("coding_agent_playbook", "rules")  # doctest: +SKIP
        PosixPath('/repo/content/core/rules')
    """
    layer_root = bundled_layer_root(layer)
    if layer_root is None:
        return None
    candidate = layer_root / subdir
    return candidate if candidate.is_dir() else None


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


def _read_config_file(path: Path) -> dict[str, Any]:
    """Parse one config file, refusing every shape ``Config`` would misread (SPEC §7.1).

    Each file is checked on its own, before the SPEC §7.2 deep merge, so a
    :class:`~coding_agent_playbook.config.ConfigError` names the file that holds
    the mistake (``.coding-agent-playbook.local.toml: [project] must be a table …``):
    a file ``tomllib`` cannot read (:func:`_decode_config_file`), an enabled-list
    shape, a table ``Config`` reads that is not one, or a malformed ``[output]``
    (``config.check_config_file``). Checked merged instead, a local
    ``project = "x"`` was reported against the committed file.
    """
    data = _decode_config_file(path)
    check_config_file(data, source=path.name)
    return data


def _decode_config_file(path: Path) -> dict[str, Any]:
    """``tomllib.load`` of ``path``, a file it cannot read raised as a ``ConfigError`` naming it.

    Bad syntax, a non-UTF-8 byte and values nested past Python's recursion limit
    (``tomllib`` recurses into inline arrays/tables) each ended every command
    with a traceback (exit 1); the CLI now prints ``error: <file>: …`` (exit 2).

    Example::

        >>> _decode_config_file(Path("broken.toml"))  # doctest: +SKIP
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.ConfigError: broken.toml: invalid TOML: Invalid value (at end of document)
    """
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name}: invalid TOML: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(
            f"{path.name}: not UTF-8 text ({exc.reason} at byte {exc.start}); save it as UTF-8"
        ) from exc
    except RecursionError as exc:
        raise ConfigError(
            f"{path.name}: inline arrays/tables nested too deeply for Python's TOML reader "
            "(it hit the recursion limit); flatten them"
        ) from exc


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
        """Read the committed config with the local overrides merged on top (SPEC §7.2).

        This is the *effective* config every command runs with, and it is never
        saved: writing it back would commit one engineer's personal overrides for
        the whole team (what ``init`` and ``check --refresh`` did before v0.18).
        Rewrites of the committed file go through ``commands/_committed_config``,
        which starts from the committed table alone (SPEC §7.2).

        Raises :class:`FileNotFoundError` without the committed file and
        :class:`~coding_agent_playbook.config.ConfigError` for a shape ``Config``
        would misread — before anything else runs. Each file is checked on its
        own first, so the error names the file at fault; what only the merged
        table can lack (a required key missing from both files) names the
        committed file, where it belongs.
        """
        return self._merged_config(self.read_committed_config_table(), source=self._CONFIG_FILENAME)

    def preview_config(self, table: Mapping[str, Any]) -> Config:
        """What :meth:`load_config` will return once ``save_config_table(table)`` ran.

        ``table`` with the checked local file merged on top (SPEC §7.2), through
        ``Config.from_dict`` — and nothing written. ``init`` and ``check
        --refresh`` call it before writing, so their final guard is the config the
        next command will load. The local file's own shape is refused when it is
        read, naming it (``.coding-agent-playbook.local.toml: [project] must be a
        table …``); ``table`` is checked by the caller, so a ``ConfigError`` raised
        by the merge itself names the local file too.

        Example::

            >>> state.preview_config(rewrite.table).commit_output  # doctest: +SKIP
            False
        """
        return self._merged_config(dict(table), source=self._CONFIG_LOCAL_FILENAME)

    def _merged_config(self, committed: dict[str, Any], *, source: str) -> Config:
        """``Config`` of ``committed`` with the checked local file merged on top (SPEC §7.2)."""
        return Config.from_dict(_deep_merge(committed, self.load_local_overrides()), source=source)

    def read_committed_config_table(self) -> dict[str, Any]:
        """The checked, decoded ``.coding-agent-playbook.toml`` alone — no local overrides.

        Holds every top-level key, including those ``Config`` does not manage
        (``[links]``, ``[metrics]``, …), so a rewrite of the committed file can
        carry them over (``config_entries.unmanaged_config_entries``). Raises
        :class:`FileNotFoundError` without the file and
        :class:`~coding_agent_playbook.config.ConfigError` naming it for a shape
        ``Config`` would misread, like :meth:`load_config`.

        Example::

            >>> source = FileSystemStateSource(repo_root=Path("/no/such/repo"))
            >>> source.read_committed_config_table()  # doctest: +ELLIPSIS
            Traceback (most recent call last):
            ...
            FileNotFoundError: missing .coding-agent-playbook.toml; run `playbook init`
        """
        primary = self._repo_root / self._CONFIG_FILENAME
        if not primary.is_file():
            raise FileNotFoundError(f"missing {primary.name}; run `playbook init`")
        return _read_config_file(primary)

    def has_committed_config(self) -> bool:
        """Whether ``.coding-agent-playbook.toml`` exists (a first ``init`` has none).

        Example::

            >>> FileSystemStateSource(repo_root=Path("/no/such/repo")).has_committed_config()
            False
        """
        return (self._repo_root / self._CONFIG_FILENAME).is_file()

    def load_local_overrides(self) -> dict[str, Any]:
        """The checked ``.coding-agent-playbook.local.toml`` table, ``{}`` when absent.

        ``playbook init`` calls it up front, before writing anything: to check the
        local file on its own and to read the overlays its final sync will use.

        Example::

            >>> FileSystemStateSource(repo_root=Path("/no/such/repo")).load_local_overrides()
            {}
        """
        local = self._repo_root / self._CONFIG_LOCAL_FILENAME
        return _read_config_file(local) if local.is_file() else {}

    def save_config(self, config: Config) -> None:
        """Atomically write ``config.to_dict()`` — and nothing else — to the committed file.

        The :class:`StateSource` contract. It drops every entry ``Config`` does not
        own (``[links]``, ``[metrics]``, ``[project] homepage``), so no command
        calls it: ``init`` and ``check --refresh`` write through
        :meth:`save_config_table`, from ``commands/_committed_config``.

        Example::

            >>> state.save_config(config)  # doctest: +SKIP
        """
        self.save_config_table(config.to_dict())

    def save_config_table(self, table: Mapping[str, Any]) -> None:
        """Atomically write the decoded ``table`` to the committed file, every entry as is.

        The committed file's only writer. Production code calls it only from
        ``commands/_committed_config.ConfigRewrite.save``, whose table is built
        from the committed file alone (pinned by
        ``tests/unit/test_committed_config.py``): never write :meth:`load_config`'s
        merged config back (SPEC §7.2). Values survive; comments and layout do not.

        Example::

            >>> state.save_config_table({**state.read_committed_config_table(), "detector_cache": {}})  # doctest: +SKIP
        """
        _atomic_write_text(self._repo_root / self._CONFIG_FILENAME, dump_toml(table))

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
            dump_toml(lockfile.to_dict()),
        )
