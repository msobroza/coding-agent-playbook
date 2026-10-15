"""Kill switches, escape hatches and pragmas (specs/prK-lifecycle-hooks.md §D.7, D-11).

Hatches are read **only** from the dispatcher's own environment, with exact
values (``PLAYBOOK_HOOKS=off``, not ``OFF``): never from a parsed command's
``VAR=1 cmd`` prefix, ``guard_config`` or ``CLAUDE_ENV_FILE``.

Claude Code also copies every settings-file ``env`` key into the hook
environment, and an agent can edit a settings file. So whenever a hatch is in
effect, the ``env`` objects of the settings files Claude loads are read (the
rare path, about 1 ms) and a hatch they set to the same value is ignored and
reported as ``escape_via_settings_env``: a deliberate human override belongs in
the launching shell. A settings file too large to read fails safe (every
present hatch is ignored), since Claude would still apply its ``env``.

A pragma (``playbook: allow-secret``, ``playbook: trusted-artifact``) counts
only when the same line is already committed at ``HEAD``, so an agent cannot
waive a guard by writing the waiver.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._config_reader import FileTooLarge, read_small_file

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.git import GitPort

__all__ = [
    "ALLOW_GENERATED_EDIT_VAR",
    "GATE_VAR",
    "HATCH_VARS",
    "HOOKS_DISABLE_VAR",
    "HOOKS_VAR",
    "SETTINGS_MAX_BYTES",
    "EscapeHatches",
    "pragma_at_head",
    "read_escape_hatches",
    "settings_files",
]

HOOKS_VAR: Final = "PLAYBOOK_HOOKS"
GATE_VAR: Final = "PLAYBOOK_GATE"
ALLOW_GENERATED_EDIT_VAR: Final = "PLAYBOOK_ALLOW_GENERATED_EDIT"
HOOKS_DISABLE_VAR: Final = "PLAYBOOK_HOOKS_DISABLE"
#: Every hatch, in the order they are reported.
HATCH_VARS: Final = (ALLOW_GENERATED_EDIT_VAR, GATE_VAR, HOOKS_VAR, HOOKS_DISABLE_VAR)
#: The one value each on/off hatch accepts.
_EXACT: Final = {HOOKS_VAR: "off", GATE_VAR: "off", ALLOW_GENERATED_EDIT_VAR: "1"}
#: Settings files above this are not parsed, and every present hatch is ignored.
SETTINGS_MAX_BYTES: Final = 16 * 1024 * 1024

type SettingsEnv = dict[str, set[str]]


@dataclass(frozen=True, slots=True)
class EscapeHatches:
    """The hatches in effect for this hook process.

    ``via_settings_env`` names the hatches ignored because a settings file
    sets them; the decision log records ``escape_via_settings_env`` for them.

    Example::

        >>> EscapeHatches(gate_off=True).used
        ('PLAYBOOK_GATE',)
    """

    hooks_off: bool = False
    gate_off: bool = False
    allow_generated_edit: bool = False
    disabled_ids: frozenset[str] = frozenset()
    via_settings_env: tuple[str, ...] = ()

    @property
    def used(self) -> tuple[str, ...]:
        """The variables in effect, for the ``escape`` decision-log line."""
        flags = {
            ALLOW_GENERATED_EDIT_VAR: self.allow_generated_edit,
            GATE_VAR: self.gate_off,
            HOOKS_VAR: self.hooks_off,
            HOOKS_DISABLE_VAR: bool(self.disabled_ids),
        }
        return tuple(name for name in HATCH_VARS if flags[name])

    def skips(self, hook_id: str, *, mandatory: bool) -> bool:
        """Whether ``PLAYBOOK_HOOKS_DISABLE`` skips ``hook_id``; never a mandatory hook (§B.2)."""
        return not mandatory and hook_id in self.disabled_ids


def read_escape_hatches(
    env: Mapping[str, str], *, settings_files: Callable[[], Sequence[Path]]
) -> EscapeHatches:
    """The hatches ``env`` (the hook process environment) puts in effect.

    ``settings_files`` is called only when some hatch would take effect, so
    an ordinary dispatch never touches a settings file.

    Example::

        >>> read_escape_hatches({"PLAYBOOK_GATE": "off"}, settings_files=lambda: ()).gate_off
        True
    """
    present = {name: env[name] for name in HATCH_VARS if _effective(name, env.get(name))}
    if not present:
        return EscapeHatches()
    defined = _settings_env(settings_files())
    ignored = tuple(
        name for name in present if defined is None or present[name] in defined.get(name, ())
    )
    kept = {name: value for name, value in present.items() if name not in ignored}
    return EscapeHatches(
        hooks_off=HOOKS_VAR in kept,
        gate_off=GATE_VAR in kept,
        allow_generated_edit=ALLOW_GENERATED_EDIT_VAR in kept,
        disabled_ids=_ids(kept.get(HOOKS_DISABLE_VAR, "")),
        via_settings_env=ignored,
    )


def settings_files(
    repo: RepoInfo | None, *, project_dir: str, env: Mapping[str, str], home: str
) -> tuple[Path, ...]:
    """The settings files whose ``env`` Claude Code applies to hook processes.

    The project's ``settings.json`` and ``settings.local.json``; for a linked
    worktree also the main checkout's ``settings.local.json`` (where Claude
    Code ≥ 2.1.211 keeps it); and ``${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json``.
    Reading one more candidate than Claude does can only ignore a hatch,
    which is the safe direction.

    Example::

        >>> settings_files(None, project_dir="/r", env={}, home="/h")[-1]
        PosixPath('/h/.claude/settings.json')
    """
    project = Path(project_dir) / ".claude"
    files = [project / "settings.json", project / "settings.local.json"]
    main = _main_checkout(repo)
    if main is not None:
        files.append(main / ".claude" / "settings.local.json")
    user_dir = env.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
    files.append(Path(user_dir) / "settings.json")
    return tuple(dict.fromkeys(files))


def pragma_at_head(git: GitPort, repo_rel: str, line_text: str) -> bool:
    """Whether ``line_text`` (whitespace-stripped) is a line of ``repo_rel`` at ``HEAD``.

    A pragma added this session, or in a file absent at ``HEAD``, is not
    honored. A ``GitTimeout`` propagates to the failure policy (guards ask).

    Example::

        >>> pragma_at_head(git, "src/a.py", "KEY = x  # playbook: allow-secret")  # doctest: +SKIP
        True
    """
    wanted = line_text.strip()
    if not wanted:
        return False
    blob = git.cat_head(repo_rel)
    if blob is None:
        return False
    return any(line.strip() == wanted for line in blob.decode("utf-8", "replace").splitlines())


def _effective(name: str, value: str | None) -> bool:
    if value is None:
        return False
    if name == HOOKS_DISABLE_VAR:
        return bool(_ids(value))
    return value == _EXACT[name]


def _ids(value: str) -> frozenset[str]:
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def _main_checkout(repo: RepoInfo | None) -> Path | None:
    if repo is None or not repo.is_linked_worktree:
        return None
    common = Path(repo.common_dir)
    return common.parent if common.name == ".git" else None


def _settings_env(paths: Sequence[Path]) -> SettingsEnv | None:
    """Every string ``env`` value the files set; ``None`` when one is too large to check."""
    found: SettingsEnv = {}
    for path in paths:
        try:
            data, _ = read_small_file(path, SETTINGS_MAX_BYTES)
        except FileTooLarge:
            return None
        except (OSError, ValueError):
            continue  # absent or unreadable: Claude cannot apply it either
        for name, value in _env_object(data).items():
            found.setdefault(name, set()).add(value)
    return found


def _env_object(data: bytes) -> dict[str, str]:
    try:
        document = json.loads(data)
    except ValueError:
        return {}
    env = document.get("env") if isinstance(document, dict) else None
    if not isinstance(env, dict):
        return {}
    return {str(k): v for k, v in env.items() if isinstance(v, str)}
