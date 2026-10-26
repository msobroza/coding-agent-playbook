"""The task registry: the only place that knows the eval tasks (#302, ADR 0012).

A **task** is the eval samples of one prompt, grouped under that prompt's id. In
every layer they live at ``eval_samples/<prompt>/<name>/sample.toml``, and a
sample's id is ``<prompt>/<name>`` (``review/spot-the-bug``). This module is the
only one that walks ``eval_samples/`` directories (:func:`collect_layer_samples`,
called per layer by the filesystem artifact source) and the only one that groups
samples into tasks (:class:`TaskRegistry`, built once per run from every layer's
samples and the resolved catalog's prompt ids).

It is not the runner and judge registry (``evals.registry``), which looks up
entry points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.loader import load_eval_sample_from_dir

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.catalog.source import ArtifactSource
    from coding_agent_playbook.evals.sample import EvalSample

#: The directory name of the eval samples kind in every layer.
EVAL_SAMPLES_DIR: Final = "eval_samples"
_SAMPLE_FILE: Final = "sample.toml"
_LAYOUT: Final = "eval_samples/<prompt>/<name>/"


class TaskRegistryError(ValueError):
    """A sample or task the registry refuses, or a lookup of an unknown name.

    ``path`` is the file or directory at fault, when there is one.
    """

    def __init__(self, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.path = path


@dataclass(frozen=True)
class Task:
    """The eval samples of one prompt (``prompt_id``), sorted by sample id."""

    prompt_id: str
    samples: tuple[EvalSample, ...]


# --------------------------------------------------------------------------- #
# Discovery: one layer's eval_samples/ directory
# --------------------------------------------------------------------------- #


def collect_layer_samples(
    root: Path, source_package: str
) -> tuple[list[EvalSample], list[TaskRegistryError]]:
    """Every sample under ``root`` (a layer's ``eval_samples/``) plus one error per bad one.

    Never raises. Dot-prefixed directories and plain files (``ATTRIBUTIONS.md``)
    are skipped; a missing ``root`` has no samples.

    Example::

        >>> collect_layer_samples(Path("/no/such/eval_samples"), "engine")
        ([], [])
    """
    loaded = [
        _load_or_error(sample_dir, root, source_package)
        for task_dir in _child_dirs(root)
        for sample_dir in _sample_dirs(task_dir)
    ]
    samples = [item for item in loaded if not isinstance(item, TaskRegistryError)]
    return samples, [item for item in loaded if isinstance(item, TaskRegistryError)]


def load_layer_samples(root: Path, source_package: str) -> list[EvalSample]:
    """Every sample under ``root``, raising the first :class:`TaskRegistryError` found.

    Example::

        >>> load_layer_samples(Path("/no/such/eval_samples"), "engine")
        []
    """
    samples, errors = collect_layer_samples(root, source_package)
    if errors:
        raise errors[0]
    return samples


def load_task_sample(sample_dir: Path, *, source_package: str) -> EvalSample:
    """Load the one sample at ``sample_dir`` (``.../eval_samples/<prompt>/<name>``).

    Raises :exc:`FileNotFoundError` or :exc:`ValueError` like the loader.

    Example::

        >>> load_task_sample(Path("eval_samples/review/spot-the-bug"),
        ...     source_package="engine").prompt_id  # doctest: +SKIP
        'review'
    """
    return load_eval_sample_from_dir(
        sample_dir, task=sample_dir.parent.name, source_package=source_package
    )


def sample_layer_root(sample_toml: Path) -> Path | None:
    """The layer root holding ``<root>/eval_samples/<prompt>/<name>/sample.toml``, or ``None``.

    The path is not resolved, so a symlinked sample maps to the layer it is
    reached through.

    Example::

        >>> sample_layer_root(Path("catalog/core/eval_samples/review/t/sample.toml"))
        PosixPath('catalog/core')
    """
    parents = sample_toml.parents
    if len(parents) < 4 or parents[2].name != EVAL_SAMPLES_DIR:
        return None
    return parents[3]


def _child_dirs(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return [
        entry
        for entry in sorted(directory.iterdir())
        if entry.is_dir() and not entry.name.startswith(".")
    ]


def _sample_dirs(task_dir: Path) -> list[Path]:
    """The sample directories of ``task_dir``; the task dir itself when it is a flat sample."""
    if (task_dir / _SAMPLE_FILE).is_file():
        return [task_dir]
    return [entry for entry in _child_dirs(task_dir) if (entry / _SAMPLE_FILE).is_file()]


def _load_or_error(
    sample_dir: Path, root: Path, source_package: str
) -> EvalSample | TaskRegistryError:
    """The sample at ``sample_dir``, or why it cannot load (the old flat layout included)."""
    if sample_dir.parent == root:
        return TaskRegistryError(
            f"{sample_dir}: an eval sample sits directly in eval_samples/; move it to "
            f"{_LAYOUT}, where <prompt> is the id of the prompt it grades",
            path=sample_dir,
        )
    try:
        return load_task_sample(sample_dir, source_package=source_package)
    except (FileNotFoundError, ValueError) as exc:
        return TaskRegistryError(str(exc), path=sample_dir / _SAMPLE_FILE)


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #


class TaskRegistry:
    """Every task of one run, registered under its prompt id with its samples.

    Build it once per run with :meth:`build` (raises the first error) or
    :meth:`collect` (returns every error, for ``playbook validate``) from every
    layer's samples and the resolved catalog's prompt ids. Later layers may add
    samples to an existing task; a sample id registered twice and a task whose
    prompt does not exist are errors.

    Example::

        >>> registry = TaskRegistry.build(source.list_eval_samples(), prompt_ids)  # doctest: +SKIP
        >>> [s.id for s in registry.select("review")]  # doctest: +SKIP
        ['review/spot-the-bug', ...]
    """

    def __init__(self, prompt_ids: Iterable[str]) -> None:
        self._prompt_ids = frozenset(prompt_ids)
        self._samples_by_task: dict[str, list[EvalSample]] = {}
        self._by_id: dict[str, EvalSample] = {}

    @classmethod
    def from_catalog(cls, source: ArtifactSource, prompts: Iterable[Prompt]) -> TaskRegistry:
        """The registry of every layer's samples (``source``) against the resolved ``prompts``.

        Any artifact source works, a third-party one included. Raises the first
        load error or :class:`TaskRegistryError`.

        Example::

            >>> TaskRegistry.from_catalog(ctx.artifact_source, ctx.prompts_resolved)  # doctest: +SKIP
        """
        return cls.build(source.list_eval_samples(), (p.frontmatter.id for p in prompts))

    @classmethod
    def build(cls, samples: Iterable[EvalSample], prompt_ids: Iterable[str]) -> TaskRegistry:
        """Register every sample, raising the first :class:`TaskRegistryError`."""
        registry, errors = cls.collect(samples, prompt_ids)
        if errors:
            raise errors[0]
        return registry

    @classmethod
    def collect(
        cls, samples: Iterable[EvalSample], prompt_ids: Iterable[str]
    ) -> tuple[TaskRegistry, list[TaskRegistryError]]:
        """Register every acceptable sample; return the registry and every refusal."""
        registry = cls(prompt_ids)
        errors: list[TaskRegistryError] = []
        for sample in samples:
            try:
                registry.register(sample)
            except TaskRegistryError as exc:
                errors.append(exc)
        return registry, errors

    def register(self, sample: EvalSample) -> None:
        """Add ``sample`` to its task; raise when its id is taken or its prompt is unknown."""
        first = self._by_id.get(sample.id)
        if first is not None:
            raise TaskRegistryError(
                f"eval sample id {sample.id!r} is registered twice: by "
                f"{_where(first)} and by {_where(sample)}",
                path=sample.source_path,
            )
        if sample.prompt_id not in self._prompt_ids:
            task_dir = sample.source_path.parent.parent
            raise TaskRegistryError(
                f"{task_dir}: task directory names no prompt; {sample.prompt_id!r} is not "
                f"a prompt id in the resolved catalog",
                path=task_dir,
            )
        self._by_id[sample.id] = sample
        self._samples_by_task.setdefault(sample.prompt_id, []).append(sample)

    def tasks(self) -> list[Task]:
        """Every task, sorted by prompt id."""
        return [self.task(prompt_id) for prompt_id in sorted(self._samples_by_task)]

    def task(self, prompt_id: str) -> Task:
        """The task of ``prompt_id``; an unknown one lists the known tasks."""
        samples = self._samples_by_task.get(prompt_id)
        if samples is None:
            raise TaskRegistryError(f"no task {prompt_id!r}; {self._known_tasks()}")
        return Task(prompt_id, tuple(sorted(samples, key=lambda s: s.id)))

    def samples_of(self, prompt_id: str) -> tuple[EvalSample, ...]:
        """The samples of the task ``prompt_id``, sorted by id."""
        return self.task(prompt_id).samples

    def sample(self, sample_id: str) -> EvalSample:
        """The sample registered as ``sample_id``; an unknown one lists the known tasks."""
        sample = self._by_id.get(sample_id)
        if sample is None:
            raise TaskRegistryError(f"no eval sample {sample_id!r}; {self._known_tasks()}")
        return sample

    def task_of(self, sample_id: str) -> Task:
        """The task the sample ``sample_id`` belongs to."""
        return self.task(self.sample(sample_id).prompt_id)

    def select(self, name: str) -> tuple[EvalSample, ...]:
        """``<task>`` selects every sample of the task, ``<task>/<name>`` that one sample."""
        if "/" in name:
            return (self.sample(name),)
        return self.samples_of(name)

    def _known_tasks(self) -> str:
        known = ", ".join(sorted(self._samples_by_task)) or "(none)"
        return f"known tasks: {known}"


def _where(sample: EvalSample) -> str:
    return f"{sample.source_package} ({sample.source_path})"


__all__ = [
    "EVAL_SAMPLES_DIR",
    "Task",
    "TaskRegistry",
    "TaskRegistryError",
    "collect_layer_samples",
    "load_layer_samples",
    "load_task_sample",
    "sample_layer_root",
]
