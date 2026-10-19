"""What ``playbook init`` writes to the committed config, planned and checked.

Split out of ``commands/init.py`` (CP-2, specs/prT-package-layout.md AC.5.5), verbatim.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.commands._init_adapters import adapters_union
from coding_agent_playbook.config.committed import (
    ConfigRewrite,
    detector_cache_table,
    plan_committed_update,
    plan_first_config,
)
from coding_agent_playbook.config.model import Config, OutputConfig, ProjectMeta, StorageConfig
from coding_agent_playbook.detector.facts import detect

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.commands._init_answers import Answers
    from coding_agent_playbook.config.files import ConfigFiles


def plan_config(files: ConfigFiles, repo_root: Path, answers: Answers) -> ConfigRewrite:
    """What ``init`` will write to ``.coding-agent-playbook.toml``, checked; nothing written.

    An existing file is rewritten from **itself alone**: never from
    ``ConfigFiles.load``, whose merge with the gitignored
    ``.coding-agent-playbook.local.toml`` (SPEC §7.2) would commit one engineer's
    personal overrides — adapters, overlays, ``[user_choices]``, ``[output]`` —
    for the whole team. On a re-run:

    * the keys ``Config`` owns are replaced, not merged, by the updated committed
      ``Config`` (:func:`_apply_answers`), so an emptied or omitted ``--overlays``
      (both mean no overlays), a dropped description or a stale
      ``[detector_cache]`` entry stays dropped. Owned: every top-level key in
      ``config.entries.CONFIG_MANAGED_KEYS``, ``[detector_cache]`` and ``[user_choices]``
      whole, and the keys ``Config`` reads inside ``[project]``/``[engine]``/
      ``[storage]``/``[output]`` (``config.entries.CONFIG_MANAGED_TABLE_KEYS``);
    * everything else is written back as parsed (it rides along in
      ``Config.extra_tables``, P6): other top-level keys (``[hooks]``,
      ``[guardrails]``, ``[links]``, ``[metrics]``, future tables, which their
      commands read from the raw TOML) and unknown keys inside those four tables
      (``[project] homepage``) — except ``[hooks] enabled``, which takes the hooks
      answer (:func:`_with_hooks_answer`).

    Values survive; comments and layout do not (the file is re-serialized).
    ``[output] commit`` is always written explicitly (``false`` unless the file
    already chose otherwise) so the output policy is discoverable.

    Raises ``ConfigError`` (exit 2) for a committed file ``Config`` would misread
    — including one missing a required key (``[engine] version``…) that only the
    local file supplies: init neither copies that personal value into the
    committed file nor guesses a team-wide one. Last, the planned config with
    the local file merged on top must load (``ConfigFiles.preview``):
    only init's final sync would otherwise load it, after the committed files
    were rewritten. Both paths are ``config.committed``'s, which ``check
    --refresh`` shares.
    """
    detector_cache = detector_cache_table(detect(repo_root))
    hooks = answers["hooks"]
    if not files.has_committed():
        fresh = _fresh_config(answers, detector_cache)
        return plan_first_config(files, _with_hooks_answer(fresh, hooks))
    return plan_committed_update(
        files,
        lambda committed: _with_hooks_answer(
            _apply_answers(committed, answers, detector_cache), hooks
        ),
    )


def _project_meta(answers: Answers) -> ProjectMeta:
    """The ``[project]`` table init writes, straight from the answers."""
    return ProjectMeta(
        name=answers["name"], kind=answers["kind"], description=answers["description"]
    )


def _with_hooks_answer(config: Config, answer: bool | None) -> Config:
    """``config`` with ``[hooks] enabled`` set through ``extra_tables`` (P6), other keys kept.

    No explicit ``answer`` keeps an ``enabled`` the committed table already
    has (a re-run never flips an earlier choice), else enables hooks.

    Example::

        _with_hooks_answer(config, False).extra_tables["hooks"]["enabled"]  # False
    """
    existing = config.extra_tables.get("hooks")
    table = dict(existing) if isinstance(existing, dict) else {}
    if answer is None and "enabled" in table:
        return config
    table["enabled"] = True if answer is None else answer
    return dataclasses.replace(config, extra_tables={**config.extra_tables, "hooks": table})


def _fresh_config(answers: Answers, detector_cache: dict[str, object]) -> Config:
    """The config for a repo with no committed file yet (``[output] commit = false``)."""
    return Config(
        schema_version=1,
        project=_project_meta(answers),
        engine_version=_engine_version,
        overlays_enabled=list(answers["overlays"]),
        adapters_enabled=list(answers["adapters"]),
        storage=StorageConfig(),
        detector_cache=detector_cache,
        output=OutputConfig(commit=False),
    )


def _apply_answers(
    committed: Config, answers: Answers, detector_cache: dict[str, object]
) -> Config:
    """``committed`` updated by a re-run: what each managed field becomes.

    ``[project]`` and ``overlays_enabled`` come from the answers, the adapters are
    :func:`~coding_agent_playbook.commands._init_adapters.adapters_union`,
    ``[detector_cache]`` is fresh, ``[output]`` is kept
    (else ``commit = false``); ``[engine]``, ``[storage]`` and the committed
    ``[user_choices]`` are kept as they are.

    Example::

        >>> _apply_answers(committed, answers, {}).overlays_enabled  # doctest: +SKIP
        []
    """
    return dataclasses.replace(
        committed,
        project=_project_meta(answers),
        adapters_enabled=adapters_union(committed.adapters_enabled, answers["adapters"]),
        overlays_enabled=list(answers["overlays"]),
        detector_cache=detector_cache,
        output=committed.output if committed.output is not None else OutputConfig(commit=False),
    )
