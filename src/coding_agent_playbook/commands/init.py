"""`playbook init` — interactive (or flag-driven) bootstrap for a fresh repo
(SPEC §12.1).

It also asks whether to enable assistant lifecycle hooks and writes the answer
as ``[hooks] enabled`` (specs/prK-lifecycle-hooks.md §B.1, OQ-3): an absent
table means off, so an engine upgrade never switches executable hooks on.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.roots import canonical_overlay_list, catalog_root
from coding_agent_playbook.commands._init_answers import collect_answers
from coding_agent_playbook.commands._init_config_plan import plan_config
from coding_agent_playbook.commands._init_overlays import (
    overlay_lists_to_check,
    refuse_unusable_overlays,
    warn_deprecated_flag_overlays,
)
from coding_agent_playbook.config.files import CONFIG_FILENAME, CONFIG_LOCAL_FILENAME, ConfigFiles
from coding_agent_playbook.precommit import write_pre_commit
from coding_agent_playbook.sync import pipeline as _sync

if TYPE_CHECKING:
    import argparse


#: The three git hook types a ``commit = false`` repo needs installed.
_HOOK_INSTALL_COMMAND = (
    "pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge"
)

_GITIGNORE_LINE = CONFIG_LOCAL_FILENAME


def _write_local_config(files: ConfigFiles) -> Path:
    """Create an empty ``.coding-agent-playbook.local.toml`` if missing.

    The file is gitignored so personal/local overrides don't pollute the
    repo. The empty file is enough for the load path to find it.
    """
    target = files.local_path
    if not target.is_file():
        target.write_text("[user_choices]\n", encoding="utf-8")
    return target


def _append_to_gitignore(repo_root: Path) -> Path:
    gitignore = repo_root / ".gitignore"
    if gitignore.is_file():
        content = gitignore.read_text(encoding="utf-8")
        if _GITIGNORE_LINE in content:
            return gitignore
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{_GITIGNORE_LINE}\n"
    else:
        content = f"{_GITIGNORE_LINE}\n"
    gitignore.write_text(content, encoding="utf-8")
    return gitignore


def _has_trailer_rows(repo_root: Path) -> bool:
    """Whether the committed config sets a commit-trailer row (prK §E.4); ``False`` if unreadable.

    The final sync reports a config it cannot read; the starter simply leaves the
    commit-msg entry out (an existing ``.pre-commit-config.yaml`` is never touched).
    """
    from coding_agent_playbook.commands.twins.policy import commit_trailer_policy

    try:
        return commit_trailer_policy(repo_root).has_rows
    except (ValueError, OSError, KeyError, TypeError):
        return False


def _uses_commitizen(repo_root: Path) -> bool:
    """Whether the repo opted into a commitizen convention (``playbook ci``'s predicate, §F.5).

    An unreadable ``pyproject.toml`` or config counts as opted in, as for CI.
    """
    from coding_agent_playbook.commands.twins.policy import commit_convention_configured

    return commit_convention_configured(repo_root)


def run(args: argparse.Namespace) -> int:
    """Bootstrap the repo: write the config files and pre-commit hooks, then sync.

    Exit 2, before writing anything, on a usage error: missing flags, an unusable
    overlay in ``--overlays`` (what the committed file gets) or in the local
    file's ``overlays_enabled`` (what the final sync uses), or (raised as
    ``ConfigError``) a config file the engine would misread. Both files are read
    and checked here — the local one on its own, the committed one on its own,
    then the config the final sync will load (:func:`plan_config`) — so a broken
    file of either kind leaves the repo untouched. A broken install exits 2
    before writing too: :func:`catalog_root` raises
    ``CatalogMissingError`` when the engine's catalog is missing,
    and ``cli.main`` reports it. A deprecated
    ``coding_agent_playbook.packs.*`` name in ``--overlays`` is written in its
    canonical ``plugins`` spelling (on a re-run too: the migration path for the
    committed file) and warned about once the overlay preflight passes.
    """
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    answers = collect_answers(args)
    answers["overlays"], deprecated_flags = canonical_overlay_list(answers["overlays"])
    files = ConfigFiles(repo_root)
    local = files.local_overrides()
    catalog_root()  # a broken install raises here: never a half-initialized repo
    refused = [
        refuse_unusable_overlays(overlays, origin)
        for overlays, origin in overlay_lists_to_check(answers, local)
    ]
    if any(refused):
        return 2
    warn_deprecated_flag_overlays(deprecated_flags)
    plan = plan_config(files, repo_root, answers)

    # Nothing is written above this line.
    config = plan.save(files)
    local_path = _write_local_config(files)
    gitignore_path = _append_to_gitignore(repo_root)
    # The starter switches matter only for a fresh config (a merge ignores them),
    # so the predicates parse config/pyproject only then, as before the N9 move.
    fresh_pre_commit = not (repo_root / ".pre-commit-config.yaml").is_file()
    pre_commit_path, pre_commit_messages = write_pre_commit(
        repo_root,
        output_commit=config.commit_output,
        commit_trailers=fresh_pre_commit and _has_trailer_rows(repo_root),
        commitizen=fresh_pre_commit and _uses_commitizen(repo_root),
    )

    print(f"Wrote {CONFIG_FILENAME}")
    print(f"Wrote {local_path.name}")
    print(f"Updated {gitignore_path.name}")
    print(f"Updated {pre_commit_path.name}")
    for message in pre_commit_messages:
        print(message, file=sys.stderr)
    if not config.commit_output:
        # Generated output is gitignored ([output] commit = false): the
        # post-checkout/post-merge hooks are what re-render it for teammates.
        print(f"Install the git hooks with: {_HOOK_INSTALL_COMMAND}")

    # Final step: invoke ``playbook sync`` so the consumer's first call lands real
    # output. Use the typed programmatic entry point (``sync.execute``) so
    # we don't have to fake an argparse.Namespace.
    return _sync.execute(repo_root=repo_root, check=False)
