"""The content digests recorded per eval sample: the sample's and its prompt's (tickets 07, 09).

:func:`sample_digest` covers the experiment a sample defines apart from the
prompt text: its ``sample.toml`` bytes and every file of its ``setup/`` tree (the
starting repo state). A change to either makes two release metrics of that
sample not comparable. :func:`prompt_digest` is the graded prompt's
:func:`~coding_agent_playbook.catalog.digest.artifact_digest`, the digest sync
and release manifests record, so a score can be tied to the prompt text it graded.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.digest import artifact_digest
from coding_agent_playbook.catalog.prompt_sets import DEFAULT_PROMPT_SET
from coding_agent_playbook.evals.prompting import render_prompt, resolve_sample_prompt
from coding_agent_playbook.lockfile.canonical_json import canonical_json

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coding_agent_playbook.catalog.prompt_sets import PromptSet
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.release.edition import Edition

#: Bytecode caches a local run may leave in ``setup/``; they are not part of the sample.
_SKIPPED_DIRS: Final = frozenset({"__pycache__"})
_SKIPPED_SUFFIXES: Final = (".pyc", ".pyo")


def sample_digest(sample: EvalSample) -> str:
    """The sha256 hex digest of ``sample.toml`` and the ``setup/`` tree beside it.

    A missing ``sample.toml`` (a sample built in memory) hashes as empty bytes.

    Example::

        >>> sample_digest(sample)  # doctest: +SKIP
        '9b1f...'
    """
    sample_toml = sample.source_path
    payload = {
        "sample": _file_sha256(sample_toml) if sample_toml.is_file() else _sha256(b""),
        "setup": _tree_hashes(sample_toml.parent / "setup"),
    }
    return _sha256(canonical_json(payload))


def prompt_digest(
    sample: EvalSample,
    prompt_set: PromptSet = DEFAULT_PROMPT_SET,
    *,
    edition: Edition | None = None,
) -> str | None:
    """The ``artifact_digest`` of the prompt ``sample`` grades, ``None`` when it resolves to none.

    With ``edition``, the digest of the edition's frozen prompt.

    Example::

        >>> prompt_digest(sample)  # doctest: +SKIP
        '5f3c...'
    """
    prompt = resolve_sample_prompt(sample, prompt_set, edition)
    return artifact_digest(prompt) if prompt is not None else None


def rendered_prompt_digest(sample: EvalSample, edition: Edition) -> str:
    """The sha256 hex digest of the prompt text ``sample`` renders from ``edition``.

    A pin records it (``release.edition_digests``), so an engine change that
    alters what a pinned sample puts in front of the agent fails the offline
    edition checks. Raises ``PromptResolutionError`` like :func:`render_prompt`.

    Example::

        >>> rendered_prompt_digest(sample, load_edition(root))  # doctest: +SKIP
        '7d0e...'
    """
    return _sha256(render_prompt(sample, strict=True, edition=edition).encode("utf-8"))


def _tree_hashes(root: Path) -> dict[str, str]:
    """``{posix path under root: sha256}`` of every regular file under ``root``."""
    return {path.relative_to(root).as_posix(): _file_sha256(path) for path in _files_under(root)}


def _files_under(root: Path) -> Iterator[Path]:
    """Every regular file under ``root``, sorted, without following directory symlinks."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in _SKIPPED_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if not name.endswith(_SKIPPED_SUFFIXES) and path.is_file():
                yield path


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
