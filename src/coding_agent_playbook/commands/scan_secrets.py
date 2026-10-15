"""``playbook scan-secrets`` — the secret guards' off-workstation twin (specs/prK-hook-pack.md §E.4).

``[--staged | --range A..B | --worktree | PATHS]`` (``_secret_scope``; with
none, ``<merge base with the default branch>..HEAD``). It is what the
``playbook-secrets`` pre-commit entry (``--staged``) and the ``scan-secrets``
row of ``playbook ci`` (``--range <merge base>..HEAD``) run:

- Tokens are found by ``security.secrets``, the in-session guard's own rules,
  and reported **masked**: rule, place and match length, never a character
  of the value.
- Credential files (``security.paths``) are flagged **by path and never
  read**: a staged ``config/credentials.json``, an untracked, non-ignored
  ``.env.prod``. Their diff lines are dropped unscanned.
- ``# playbook: allow-secret <rule-id>`` waives its line only when that line
  is already committed at the base revision; a new one is reported.
- The path policy is the engine catalog extended by ``[guardrails.secrets]``
  (``extra_globs`` add, ``allow_paths`` exempt fixtures) **as committed at
  the base**, so a change cannot exempt itself; ``.local.toml`` never applies.
- An untracked symlink is never followed; a file over 32 MiB is noted, not read.

Exit codes: 0 clean (notes only), 1 a token or a credential file, 2 a usage,
policy or git error.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._git_base import open_git
from coding_agent_playbook.commands._secret_scope import (
    SecretScope,
    paths_scope,
    range_scope,
    staged_scope,
    worktree_scope,
)
from coding_agent_playbook.hook_runtime.git import GitError
from coding_agent_playbook.hooks_config import parse_guardrails_config
from coding_agent_playbook.security.files import user_home
from coding_agent_playbook.security.paths import DEFAULT_PATH_POLICY, PathPolicy
from coding_agent_playbook.security.secrets import SecretFinding, scan_added_lines, scan_text

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.hook_runtime.git import GitPort, SafeGit

__all__ = ["SecretHit", "SecretReport", "load_path_policy", "run", "scan_scope"]

CONFIG_FILE: Final = ".coding-agent-playbook.toml"
#: Larger working-tree files are noted, never read (a CLI may be slow, not unbounded).
MAX_FILE_BYTES: Final = 32 * 1024 * 1024
ADVICE: Final = "Use an env var or the secret manager and reference it by name."
SECRET_PATH_RULE: Final = "secret-path"
SECRET_PATH_DETAIL: Final = (
    "a credential file; gitignore it and commit only an .env.example of variable names"
)
NEW_PRAGMA: Final = "; its allow-secret pragma is new: it counts only once committed"


@dataclass(frozen=True, slots=True, order=True)
class SecretHit:
    """One blocking finding (``line`` 0: the whole file); ``detail`` holds no secret character.

    Example: ``SecretHit(".env.prod", 0, "secret-path", SECRET_PATH_DETAIL)``.
    """

    path: str
    line: int
    rule: str
    detail: str

    def text(self) -> str:
        """``path[:line]: rule: detail``."""
        where = self.path if self.line == 0 else f"{self.path}:{self.line}"
        return f"{where}: {self.rule}: {self.detail}"

    def to_json(self) -> dict[str, object]:
        return {"path": self.path, "line": self.line, "rule": self.rule, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class SecretReport:
    """What a scan found: blocking hits (sorted by path, line) and non-blocking notes."""

    hits: tuple[SecretHit, ...]
    notes: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        """``1`` when anything blocks, else ``0``."""
        return 1 if self.hits else 0


def run(args: argparse.Namespace, *, git: SafeGit | None = None) -> int:
    """Scan the selected scope and print the masked findings; returns 0, 1 or 2.

    Example::

        >>> run(build_parser().parse_args(["scan-secrets", "--staged"]))  # doctest: +SKIP
        1
    """
    repo_root = Path(args.repo_root or ".").resolve()
    if args.paths and (args.staged or args.worktree or args.rev_range is not None):
        print(
            "error: pass PATHS or one of --staged, --range, --worktree, not both", file=sys.stderr
        )
        return 2
    try:
        port = git if git is not None else open_git(repo_root)
        scope = _scope(port, args, repo_root)
        policy = load_path_policy(port, scope.base)
        root = Path(port.repo.worktree_root)
        report = scan_scope(port, scope, policy, root=root, home=user_home())
    except (GitError, ValueError) as exc:  # GitBaseError and policy errors are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(_json(report, scope.label) if args.format == "json" else _text(report, scope.label))
    return report.exit_code


def load_path_policy(git: GitPort, base: str | None) -> PathPolicy:
    """The engine catalog extended by ``[guardrails.secrets]`` as committed at ``base``.

    Raises ``ValueError`` naming a malformed config or key.

    Example::

        >>> load_path_policy(git, None) == DEFAULT_PATH_POLICY  # doctest: +SKIP
        True
    """
    raw = None if base is None else git.show(base, CONFIG_FILE)
    secrets = parse_guardrails_config(_guardrails_table(raw)).secrets
    return DEFAULT_PATH_POLICY.extended(deny=secrets.extra_globs, allow=secrets.allow_paths)


def scan_scope(
    git: GitPort,
    scope: SecretScope,
    policy: PathPolicy,
    *,
    root: Path,
    home: str,
    platform: str = sys.platform,
) -> SecretReport:
    """Classify the scope's paths, scan its lines and files, and judge pragmas at the base.

    ``root`` is the worktree root the scope's paths are relative to.

    Example::

        >>> scan_scope(git, staged_scope(git), DEFAULT_PATH_POLICY, root=Path("."),
        ...            home="/h").exit_code  # doctest: +SKIP
        0
    """
    secret = _secret_paths(scope, policy, root, home=home, platform=platform)
    added = [line for line in scope.added if line.path not in secret]
    texts = {(line.path, line.line): line.text for line in added}
    found = [(f, texts.get((f.path, f.line), "")) for f in scan_added_lines(added)]
    notes: list[str] = []
    for rel in scope.files:
        if rel not in secret:
            found += _scan_file(root, rel, notes)
    base_lines = _BaseLines(git, scope.base)
    hits = [SecretHit(rel, 0, SECRET_PATH_RULE, SECRET_PATH_DETAIL) for rel in secret]
    hits += [hit for f, text in found if (hit := _token_hit(f, text, base_lines)) is not None]
    return SecretReport(tuple(sorted(hits)), tuple(notes))


def _scope(git: SafeGit, args: argparse.Namespace, repo_root: Path) -> SecretScope:
    if args.paths:
        return paths_scope(git, args.paths, repo_root)
    if args.staged:
        return staged_scope(git)
    if args.worktree:
        return worktree_scope(git)
    return range_scope(git, args.rev_range)


def _guardrails_table(raw: bytes | None) -> object:
    """The ``[guardrails]`` table of a committed config (``None``: absent)."""
    import tomllib

    if raw is None:
        return None
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{CONFIG_FILE} at the base revision is not valid TOML: {exc}") from None
    return doc.get("guardrails")


def _secret_paths(
    scope: SecretScope, policy: PathPolicy, root: Path, *, home: str, platform: str
) -> frozenset[str]:
    """Changed paths and files that name a credential file; a file also by its link target."""
    named = {
        rel
        for rel in (*scope.changed, *scope.files)
        if policy.matches(rel, home=home, platform=platform)
    }
    named.update(
        rel
        for rel in scope.files
        if policy.matches(os.path.realpath(root / rel), home=home, platform=platform)
    )
    return frozenset(named)


def _scan_file(root: Path, rel: str, notes: list[str]) -> list[tuple[SecretFinding, str]]:
    """The findings of one working-tree file with each finding's line text; a skip is a note."""
    path = root / rel
    if path.is_symlink():
        notes.append(f"{rel}: a symlink; not followed")
        return []
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            notes.append(f"{rel}: larger than {MAX_FILE_BYTES // (1024 * 1024)} MiB; not scanned")
            return []
        with path.open("rb") as handle:
            text = handle.read().decode("utf-8", errors="replace")
    except OSError as exc:
        notes.append(f"{rel}: cannot read ({exc.strerror})")
        return []
    lines = text.split("\n")
    return [(f, lines[f.line - 1] if f.line else "") for f in scan_text(text, rel)]


def _token_hit(finding: SecretFinding, line_text: str, base: _BaseLines) -> SecretHit | None:
    """The hit for a token, or ``None`` when an allow-secret pragma committed at the base waives it."""
    detail = f"{finding.label} ({finding.length} chars)"
    if finding.pragma:
        if line_text and base.has(finding.path, line_text):
            return None
        detail += NEW_PRAGMA
    return SecretHit(finding.path, finding.line, finding.rule_id, detail)


class _BaseLines:
    """The stripped lines of each file at the base revision, read once per file."""

    def __init__(self, git: GitPort, base: str | None) -> None:
        self._git = git
        self._base = base
        self._files: dict[str, frozenset[str]] = {}

    def has(self, path: str, line_text: str) -> bool:
        """Whether ``line_text`` (stripped) is a line of ``path`` at the base."""
        if self._base is None:
            return False
        if path not in self._files:
            blob = self._git.show(self._base, path)
            text = "" if blob is None else blob.decode("utf-8", errors="replace")
            self._files[path] = frozenset(line.strip() for line in text.splitlines())
        return line_text.strip() in self._files[path]


def _text(report: SecretReport, label: str) -> str:
    lines = [hit.text() for hit in report.hits] + [f"note: {note}" for note in report.notes]
    if not report.hits:
        return "\n".join([*lines, f"scan-secrets {label}: clean"])
    count = len(report.hits)
    plural = "" if count == 1 else "s"
    return "\n".join([*lines, ADVICE, f"scan-secrets {label}: {count} finding{plural}"])


def _json(report: SecretReport, label: str) -> str:
    document = {
        "scope": label,
        "findings": [hit.to_json() for hit in report.hits],
        "notes": list(report.notes),
        "exit": report.exit_code,
    }
    return json.dumps(document, indent=2, ensure_ascii=False)
