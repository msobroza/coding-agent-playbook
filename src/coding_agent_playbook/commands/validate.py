"""`playbook validate` — cross-reference checks (SPEC §12.6).

The command only: the rule set it runs is :mod:`coding_agent_playbook.validation.checks`
(the same rule set ``playbook sync`` runs as its gate), and the config-less context of
an engine or overlay checkout is :mod:`coding_agent_playbook.validation.context`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.orchestrator import SyncContext
from coding_agent_playbook.validation.checks import (
    collect_validation_findings,
    warn_refused_skill_files,
)
from coding_agent_playbook.validation.context import (
    config_less_context,
    config_less_notes,
    has_consumer_config,
)
from coding_agent_playbook.validation.findings import (
    report_validation_errors,
    report_validation_warnings,
)

if TYPE_CHECKING:
    import argparse


def run(args: argparse.Namespace) -> int:
    """``playbook validate``: exit 0 printing ``OK <n> artifacts validated``, else 1.

    Without a ``.coding-agent-playbook.toml`` (an engine or overlay checkout)
    it validates a config-less context and first prints which consumer-config
    checks it skipped (:mod:`coding_agent_playbook.validation.context`).
    """
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    config_less = not has_consumer_config(repo_root)
    if config_less:
        print("\n".join(config_less_notes(repo_root)))
    ctx = (
        config_less_context(repo_root)
        if config_less
        else SyncContext.from_repo(repo_root, tolerate_hook_errors=True)
    )
    findings = collect_validation_findings(ctx, config_less=config_less)
    warn_refused_skill_files(ctx.skills_resolved)
    report_validation_warnings(findings.warnings, sys.stderr)
    if findings.errors:
        report_validation_errors(findings.errors, sys.stdout)
        return 1
    artifact_count = len(ctx.rules_resolved) + len(ctx.prompts_resolved) + len(ctx.hooks_resolved)
    print(f"OK {artifact_count} artifacts validated")
    return 0
