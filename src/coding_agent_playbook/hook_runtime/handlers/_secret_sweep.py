"""The working-tree walk of stop-diff-sweep (specs/prK-hook-pack.md §E.4).

One pass over what the turn left behind: the added lines of ``git diff HEAD``
and every untracked, non-ignored file (``git ls-files --others
--exclude-standard``, so ignored files are never even listed).

- A changed or untracked credential file (the secret path policy) is flagged
  **by path** and never opened: the next ``git add -A`` would commit it.
- An untracked model or data artifact (``*.pt``, ``*.pkl``, ``*.safetensors``,
  ``*.parquet``) or any untracked file over ``large_file_mb`` is a warning, by
  ``lstat`` alone (``check-added-large-files`` is not in the air-gapped starter).
- Every other added line and untracked text file is scanned for tokens, at
  most ``max_scan_bytes`` in all; past the cap the sweep is ``partial``.
  Symlinks are not followed; binaries (a NUL in the first 8 KiB) are skipped.
- An ``allow-secret`` pragma waives a tracked line only when that line is
  committed at ``HEAD`` (``escape.pragma_at_head``); an untracked file has none.
- The PII tier (specs/prK-hook-pack.md §E.5), on only when an overlay lists
  detectors in the hook's ``pii`` key, scans the same texts within the same
  budget and reports each hit as a masked ``pii:<detector>`` line.

A private module: :mod:`.stop_sweep` turns the :class:`SweepReport` into a stage result.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.escape import pragma_at_head
from coding_agent_playbook.hook_runtime.handlers._secret_policy import (
    content_rules,
    finding_line,
    path_policy,
)
from coding_agent_playbook.security.files import user_home
from coding_agent_playbook.security.pii_findings import (
    PII_RULE_PREFIX,
    pii_line_findings,
    pii_text_findings,
)
from coding_agent_playbook.security.secrets import is_binary, scan_added_lines, scan_text

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.git.safe_git import AddedLine
    from coding_agent_playbook.security.pii import PiiConfig
    from coding_agent_playbook.security.secrets import SecretFinding

__all__ = ["ARTIFACT_SUFFIXES", "FIX", "PII_FIX", "SweepLimits", "SweepReport", "sweep_tree"]

#: Untracked artifacts that warn whatever their size (weights, pickles, tables).
ARTIFACT_SUFFIXES: Final = (".pt", ".pkl", ".safetensors", ".parquet")
FIX: Final = "remove it, move it to env or the secret manager, or gitignore it"
PII_FIX: Final = "replace it with a placeholder or a synthetic value"
_MIB: Final = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SweepLimits:
    """The byte cap over all scanned text and the large-file warning threshold."""

    max_scan_bytes: int = 2 * _MIB
    large_file_mb: int = 10


@dataclass(slots=True)
class SweepReport:
    """What one sweep found: blocking lines, warning lines, the files it scanned, ``partial``.

    ``changed`` lists the non-secret paths with new text (tracked and untracked):
    the deserialization rescan rides on it.
    """

    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    partial: bool = False


@dataclass(slots=True)
class _Budget:
    left: int
    exhausted: bool = False

    def take(self, size: int) -> bool:
        """Spend ``size`` bytes, or mark the sweep partial when they do not fit."""
        if size > self.left:
            self.exhausted = True
            return False
        self.left -= size
        return True


def sweep_tree(
    ctx: HandlerContext, root: str, limits: SweepLimits, *, pii: PiiConfig | None = None
) -> SweepReport:
    """Sweep the working tree of the repository at ``root`` (module docstring).

    ``pii`` turns the PII tier on (``None``: off, the engine default).

    Example::

        >>> sweep_tree(ctx, "/repo", SweepLimits()).blocking  # doctest: +SKIP
        ['".env.prod" secret-path; remove it, move it to env or the secret manager, ...']
    """
    added, untracked = ctx.git.diff_added(), ctx.git.ls_untracked()
    secret = _secret_names(ctx, {line.path for line in added}.union(untracked))
    report, budget = SweepReport(), _Budget(limits.max_scan_bytes)
    report.blocking.extend(f"{quote_data(rel)} secret-path; {FIX}" for rel in sorted(secret))
    lines = _within([line for line in added if line.path not in secret], budget)
    report.changed.extend(dict.fromkeys(line.path for line in lines))
    findings = _tracked_findings(lines, ctx)
    if pii is not None:
        findings.extend(pii_line_findings(lines, pii))
    for rel in (rel for rel in untracked if rel not in secret):
        findings.extend(_untracked_findings(root, rel, ctx, limits, budget, report, pii))
    report.blocking.extend(f"{finding_line(f)}; {_fix(f)}" for f in findings)
    report.partial = budget.exhausted
    return report


def _fix(finding: SecretFinding) -> str:
    return PII_FIX if finding.rule_id.startswith(PII_RULE_PREFIX) else FIX


def _secret_names(ctx: HandlerContext, rels: Iterable[str]) -> frozenset[str]:
    """The ``rels`` the rendered secret path policy names (each path matched once)."""
    policy, home = path_policy(ctx.cfg), ctx.home or user_home()
    return frozenset(rel for rel in rels if policy.matches(rel, home=home, platform=ctx.platform))


def _within(lines: Iterable[AddedLine], budget: _Budget) -> list[AddedLine]:
    """The leading ``lines`` the budget pays for."""
    kept: list[AddedLine] = []
    for line in lines:
        if not budget.take(len(line.text) + 1):
            break
        kept.append(line)
    return kept


def _tracked_findings(lines: list[AddedLine], ctx: HandlerContext) -> list[SecretFinding]:
    """Tokens on tracked added lines, minus those a pragma committed at ``HEAD`` waives."""
    texts = {(line.path, line.line): line.text for line in lines}
    found = scan_added_lines(lines, rules=content_rules(ctx.cfg))
    return [f for f in found if not (f.pragma and _vouched(f, texts, ctx))]


def _vouched(
    finding: SecretFinding, texts: dict[tuple[str, int], str], ctx: HandlerContext
) -> bool:
    text = texts.get((finding.path, finding.line), "")
    return bool(text.strip()) and pragma_at_head(ctx.git, finding.path, text)


def _untracked_findings(
    root: str,
    rel: str,
    ctx: HandlerContext,
    limits: SweepLimits,
    budget: _Budget,
    report: SweepReport,
    pii: PiiConfig | None,
) -> list[SecretFinding]:
    """One untracked file: an artifact warning, or its tokens (and PII); never a followed link."""
    path = Path(root, rel)
    try:
        status = path.lstat()
    except OSError:
        return []
    if not stat.S_ISREG(status.st_mode):
        return []  # a symlink or a special file is never followed or read
    warning = _artifact_warning(rel, status.st_size, limits)
    if warning is not None:
        report.warnings.append(warning)
        return []
    text = _read(path, status.st_size, budget)
    if text is None:
        return []
    report.changed.append(rel)
    found = scan_text(text, rel, rules=content_rules(ctx.cfg))
    return found if pii is None else [*found, *pii_text_findings(text, rel, pii)]


def _artifact_warning(rel: str, size: int, limits: SweepLimits) -> str | None:
    """The warning line for an untracked model/data artifact or large file, else ``None``."""
    large = size > limits.large_file_mb * _MIB
    if not (large or rel.lower().endswith(ARTIFACT_SUFFIXES)):
        return None
    mib = size / _MIB
    kind = "large file" if large and not rel.lower().endswith(ARTIFACT_SUFFIXES) else "artifact"
    return (
        f"{quote_data(rel)} is an untracked {kind} ({mib:.0f} MiB); "
        "gitignore it or keep it outside the repository"
    )


def _read(path: Path, size: int, budget: _Budget) -> str | None:
    """The text of ``path`` when the budget pays for it and it is not binary."""
    if not budget.take(size):
        return None
    try:
        with path.open("rb") as handle:
            data = handle.read(size)
    except OSError:
        return None
    text = data.decode("utf-8", errors="replace")
    return None if is_binary(text) else text
