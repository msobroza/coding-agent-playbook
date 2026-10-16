"""`playbook check` — diagnostic dump (SPEC §12.4). Includes ``--refresh`` per
§12.5 which writes the freshly-detected facts back into the committed config's
``detector_cache`` table; every other value in the file is kept, though the file is
re-serialized (comments and layout are lost) and no local override is written.

A diagnostic, so it exits 0 whatever it finds (drift included). An overlay in
``overlays_enabled`` that ``playbook sync`` would refuse (``_sync_preflight``) is
flagged under Environment, and the Drift section then never reports a clean state.
The Hooks block comes from :mod:`._check_hooks` (specs/prK-lifecycle-hooks.md
§A.8). The Drift lines are ``lockfile.drift_entries``, the definition the
``drift`` Stop stage shares (specs/prK-hook-pack.md §E.1), with Claude's strict
settings parser for the scoped (``json:<pointer>``) entries (§C.2.6).
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.adapters._settings_drift import settings_document, stray_launcher_edited
from coding_agent_playbook.commands import _committed_config, _sync_preflight
from coding_agent_playbook.commands._check_hooks import format_hooks_section
from coding_agent_playbook.detector import detect, evaluate_predicate
from coding_agent_playbook.lockfile import drift_entries
from coding_agent_playbook.orchestrator import SyncContext
from coding_agent_playbook.sources.filesystem import FileSystemStateSource

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence

    from coding_agent_playbook.commands._sync_preflight import UnusableOverlay
    from coding_agent_playbook.lockfile import Lockfile

_SYNC_REFUSES = "'playbook sync' refuses to run until every overlay in overlays_enabled is usable"


def _format_env_section(ctx: SyncContext, unusable: Sequence[UnusableOverlay] = ()) -> str:
    facts = ctx.facts
    python_version = facts.get("python_version", platform.python_version())
    package_manager = facts.get("package_manager", "(unknown)")
    overlays = ", ".join(ctx.config.overlays_enabled) or "(none)"
    lines = [
        "=== Environment ===",
        f"  Python: {python_version}",
        f"  Package manager: {package_manager}",
        f"  Engine: coding-agent-playbook {_engine_version}",
        f"  Overlays: {overlays}",
        *_format_unusable_overlays(unusable),
    ]
    return "\n".join(lines)


def _format_unusable_overlays(unusable: Sequence[UnusableOverlay]) -> list[str]:
    """One ``✗ <name>: <reason>`` line per unusable overlay, plus what it implies."""
    if not unusable:
        return []
    return [
        *(f"    ✗ {problem}" for problem in unusable),
        f"    {_SYNC_REFUSES}; the artifacts below omit the unusable ones.",
    ]


def _format_detected_section(ctx: SyncContext) -> str:
    facts = ctx.facts
    frameworks_dict = facts.get("frameworks", {}) or {}
    frameworks_str = (
        ", ".join(f"{name}={version}" for name, version in sorted(frameworks_dict.items()))
        or "(none)"
    )
    lines = [
        "=== Detected ===",
        f"  project_kind: {facts.get('project_kind', '(unknown)')}",
        f"  frameworks: {frameworks_str}",
        f"  has_notebooks: {facts.get('has_notebooks', False)}",
        f"  has_dockerfile: {facts.get('has_dockerfile', False)}",
        f"  has_ci: {facts.get('has_ci', False)}",
    ]
    return "\n".join(lines)


#: List-valued ``applies_if`` keys the skip reason quotes as written.
_LIST_PREDICATE_KEYS = frozenset(
    {"has_framework", "any_framework", "has_file", "has_dev_dependency"}
)


def _format_skip_reason(predicate: dict[str, object], facts: dict[str, object]) -> str:
    """Render a SPEC §12.4-style ``(skipped: ...)`` suffix for the first
    predicate key that fails. Mirrors the canonical examples:

    * boolean fact: ``(skipped: has_notebooks=False)``
    * framework check: ``(skipped: applies_if has_framework=['great-expectations'])``
    * dev dependency: ``(skipped: applies_if has_dev_dependency=['pytest-cov'])``

    We deliberately don't try to be exhaustive — we surface the first failing
    key in the order the predicate dict iterates (insertion order), since
    that's what the example shows and it's the most actionable for the user.
    """
    for key, value in predicate.items():
        if key in _LIST_PREDICATE_KEYS:
            wanted = value if isinstance(value, list) else [value]
            return f"(skipped: applies_if {key}={wanted!r})"
        if key == "python_version":
            return f"(skipped: applies_if python_version={value!r})"
        # Boolean facts (has_notebooks, has_dockerfile, has_ci, banking_mode).
        actual = facts.get(key, False)
        return f"(skipped: {key}={actual})"
    return "(skipped)"


def _format_artifacts_section(ctx: SyncContext) -> str:
    rules = ctx.rules_resolved
    prompts = ctx.prompts_resolved
    facts = ctx.facts
    rule_lines = []
    for rule in rules:
        predicate = rule.frontmatter.applies_if or {}
        applies = (
            evaluate_predicate(predicate, facts, repo_root=ctx.repo_root) if predicate else True
        )
        marker = "[✓]" if applies else "[✗]"
        suffix = (
            f"({rule.source_package}, scope={rule.frontmatter.scope})"
            if applies
            else _format_skip_reason(predicate, dict(facts))
        )
        rule_lines.append(
            f"    {marker} {rule.frontmatter.priority:02d}-{rule.frontmatter.id} {suffix}"
        )
    prompt_lines = []
    for prompt in prompts:
        predicate = prompt.frontmatter.applies_if or {}
        applies = (
            evaluate_predicate(predicate, facts, repo_root=ctx.repo_root) if predicate else True
        )
        marker = "[✓]" if applies else "[✗]"
        if applies:
            rules_note = (
                f" (includes_rules: {', '.join(prompt.frontmatter.includes_rules)})"
                if prompt.frontmatter.includes_rules
                else ""
            )
            prompt_lines.append(f"    {marker} {prompt.frontmatter.id}{rules_note}")
        else:
            prompt_lines.append(
                f"    {marker} {prompt.frontmatter.id} {_format_skip_reason(predicate, dict(facts))}"
            )
    applicable_rules = sum(
        1
        for rule in rules
        if not rule.frontmatter.applies_if
        or evaluate_predicate(rule.frontmatter.applies_if, facts, repo_root=ctx.repo_root)
    )
    applicable_prompts = sum(
        1
        for prompt in prompts
        if not prompt.frontmatter.applies_if
        or evaluate_predicate(prompt.frontmatter.applies_if, facts, repo_root=ctx.repo_root)
    )
    out = ["=== Artifacts ==="]
    out.append(f"  Rules ({applicable_rules} applicable / {len(rules)} total):")
    out.extend(rule_lines or ["    (none)"])
    out.append(f"  Prompts ({applicable_prompts} applicable / {len(prompts)} total):")
    out.extend(prompt_lines or ["    (none)"])
    return "\n".join(out)


def _format_drift_section(ctx: SyncContext, unusable: Sequence[UnusableOverlay] = ()) -> str:
    """Compare the files on disk with the lockfile.

    With an unusable overlay the state is never reported clean: a matching
    lockfile only says what the last sync wrote, and no sync can run now.
    """
    lockfile = ctx.state_source.load_lockfile()
    lines = ["=== Drift ==="]
    if lockfile is None:
        lines.append("  No lockfile yet — run 'playbook sync' to create one.")
    elif drift := _lockfile_drift(ctx, lockfile):
        lines.extend(drift)
    elif not unusable:
        lines.append("  All on-disk files match generated output.")
    else:
        lines.append("  On-disk files match the lockfile, but the state is not clean:")
    if unusable:
        lines.append(f"  {_SYNC_REFUSES} (see Environment).")
    return "\n".join(lines)


def _lockfile_drift(ctx: SyncContext, lockfile: Lockfile) -> list[str]:
    """One line per lockfile entry whose file is missing, changed, or lost its exec bit.

    A scoped entry (one managed element of a file shared with the user) is
    judged by its element, never by the whole file's hash.
    """
    items = drift_entries(
        lockfile, ctx.repo_root, parse_scoped=settings_document, edited=stray_launcher_edited
    )
    return [f"  {item.line()}" for item in items]


def _refresh(repo_root: Path) -> None:
    """Re-run the detector and write ``[detector_cache]`` — only it — to the committed config.

    The committed file is rewritten from itself alone
    (:func:`_committed_config.plan_detector_cache_refresh`): every other key
    keeps its parsed value, as written — not as ``Config`` would rewrite it —
    while comments and layout are lost; nothing from the gitignored local file
    is written. Hence its own state source rather than ``SyncContext.config``,
    which is the config *merged* with that file (and still what the report
    describes).

    Raises ``ConfigError`` (exit 2) before writing for a committed file ``Config``
    would misread on its own, e.g. one missing ``[engine] version`` that only the
    local file supplies.

    Example::

        >>> _refresh(repo_root)  # doctest: +SKIP
    """
    state = FileSystemStateSource(repo_root=repo_root)
    cache = _committed_config.detector_cache_table(detect(repo_root))
    _committed_config.plan_detector_cache_refresh(state, cache).save(state)


def run(args: argparse.Namespace) -> int:
    """Print the diagnostic report; with ``--refresh``, first rewrite ``[detector_cache]``.

    A config error (``ConfigError`` / ``FileNotFoundError``, exit 2 in ``cli.main``)
    stops it before anything is written or printed.
    """
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    ctx = SyncContext.from_repo(repo_root)
    unusable = _sync_preflight.unusable_overlays(ctx.config.overlays_enabled)
    if getattr(args, "refresh", False):
        _refresh(repo_root)
        print(f"Refreshed detector_cache in {FileSystemStateSource._CONFIG_FILENAME}.")
    print(_format_env_section(ctx, unusable))
    print(_format_detected_section(ctx))
    print(_format_artifacts_section(ctx))
    print(format_hooks_section(ctx))
    print(_format_drift_section(ctx, unusable))
    # A diagnostic: problems are reported above, never through the exit code
    # (drift exits 0 too). `playbook validate` and `playbook sync` are the gates.
    return 0
