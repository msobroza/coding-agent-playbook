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

from coding_agent_playbook._atomic_io import atomic_write_bytes
from coding_agent_playbook._layers import ENGINE_PACKAGE as ENGINE_PACKAGE
from coding_agent_playbook._layers import REPO_LOCAL_SOURCE as REPO_LOCAL_SOURCE
from coding_agent_playbook._toml import dump_toml
from coding_agent_playbook.catalog import catalog_layer_root, is_bundled_layer
from coding_agent_playbook.config import Config, ConfigError, check_config_file
from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.lockfile import Lockfile
from coding_agent_playbook.sources._hook_walk import walk_hook_layer
from coding_agent_playbook.sources.base import ArtifactSource, StateSource
from coding_agent_playbook.types import Prompt, Rule, Skill, split_frontmatter

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence
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
    reads ``<subdir>`` from its directory in the catalog root
    (``catalog.catalog_layer_root``) and is never imported. Every other
    package resolves ``<package>/resources/<subdir>`` via importlib.resources.

    Returns ``None`` if the package is not importable, has no ``resources/``
    directory, or has no matching subdirectory, so sources silently skip
    packages that ship no artifacts of a given kind (SPEC §20.3). The one raise
    is :class:`CatalogMissingError` for a bundled layer when the engine's
    catalog root is missing: a broken install must fail loudly, not render
    without the engine's artifacts.
    """
    # Outside the ``except Exception`` guard below on purpose: a missing catalog
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
    Raises :class:`CatalogMissingError` when the catalog root is missing.

    Example::

        >>> _bundled_subdir("coding_agent_playbook", "rules")  # doctest: +SKIP
        PosixPath('/repo/catalog/core/rules')
    """
    layer_root = catalog_layer_root(layer)
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
    """Write ``content`` to ``target`` atomically, as UTF-8 bytes.

    A SIGKILL or power loss mid-write leaves either the old file intact or the
    new file fully written — never a half-written one. Used for both
    ``.coding-agent-playbook.toml`` and ``.coding-agent-playbook.lock`` so a
    crashed ``playbook sync`` can be safely retried. It delegates to the byte
    writer because ``Path.write_text`` translates ``\\n`` on Windows.
    """
    atomic_write_bytes(target, content.encode("utf-8"))


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
    """Walks the engine's catalog (``catalog/core/`` and the enabled
    ``catalog/plugins/<name>/``, located by the ``catalog`` module), importlib.resources
    for overlay packages, plus <repo>/playbook/ for repo-local artifacts
    (SPEC §20.3, §11).

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

        Each layer's ``eval_tasks/`` (``catalog/core/eval_tasks/`` for the
        engine, ``catalog/plugins/<name>/eval_tasks/`` for a bundled plugin,
        ``<pkg>/resources/eval_tasks/`` for an overlay package, then
        ``<repo>/playbook/eval_tasks/``). Later layers do NOT override earlier
        ones here — the orchestrator's :class:`OverlayResolver` handles ID-based
        collision semantics for rules/prompts/skills, but eval tasks are
        aggregated as-is in v1 (no per-layer override pass yet; the
        collision-by-id pattern is identical and lands when first overlay ships
        eval tasks). Each task's ``source_package`` is its layer's label (the
        engine package, a bundled-plugin or overlay-package name, or
        ``"<repo-local>"``).
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
        (``[links]``, ``[metrics]``, ``[hooks]``, …), so a rewrite of the committed
        file can carry them over (``config_entries.unmanaged_config_entries``).
        Raises :class:`FileNotFoundError` without the file and
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

    def load_primary_config(self) -> Config:
        """The committed config alone, as a ``Config``: never merging ``.local.toml`` (P6).

        :meth:`read_committed_config_table` through ``Config.from_dict``, so its
        ``extra_tables`` hold the committed ``[hooks]``/``[guardrails]`` the hook
        policy reads (:meth:`StateSource.load_policy_tables`). Raises like
        :meth:`load_config` for a missing or misread committed file. Rewrites of
        the committed file go through ``commands/_committed_config``.

        Example::

            >>> FileSystemStateSource(repo_root=Path("/no/such/repo")).load_primary_config()
            Traceback (most recent call last):
            ...
            FileNotFoundError: missing .coding-agent-playbook.toml; run `playbook init`
        """
        return Config.from_dict(self.read_committed_config_table(), source=self._CONFIG_FILENAME)

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
        """Atomically write ``config.to_dict()`` (``extra_tables`` included) to the committed file.

        The :class:`StateSource` contract. A ``Config`` from :meth:`load_config`
        has the local file merged in, so saving it would commit personal
        overrides: no command calls this. ``init`` and ``check --refresh`` write
        through :meth:`save_config_table`, from ``commands/_committed_config``.

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
