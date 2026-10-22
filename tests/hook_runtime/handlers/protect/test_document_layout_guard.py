"""document-layout-guard: specs and plans go to the document layout (prU D60, D61, D71; L0-22).

A write of a spec or plan into a known other location (a framework's own folder
such as ``docs/superpowers/``, or a spec or plan file under the scratch directory)
is denied with a reason naming the configured directory. The hook reads its
directories from its handler config, which ``playbook sync``'s layout adapter
rewrites to the repo's ``[layout]`` (D78(12)); ``handler_config`` stands in for
that rewrite here, and the last test checks it on a real sync.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.config.layout import LAYOUT_DEFAULTS
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.handlers.protect.document_layout_guard import DEFAULT_DIRS
from tests.hook_runtime.handlers.pack_repo import engine_hook

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_runtime.handlers.pack_repo import PackRepo

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "document-layout-guard"


def _install(repo: PackRepo, config: Mapping[str, object] | None = None) -> PackRepo:
    repo.install_pack([HOOK_ID], handler_config={HOOK_ID: dict(config)} if config else None)
    return repo


def _write(repo: PackRepo, deps: RuntimeDeps, rel: str) -> SimulateReport:
    tool_input = {"file_path": str(repo.root / rel), "content": "# Plan\n"}
    return repo.simulate(repo.tool_payload("Write", tool_input), deps)


def _bash(repo: PackRepo, deps: RuntimeDeps, command: str) -> SimulateReport:
    return repo.simulate(repo.tool_payload("Bash", {"command": command}), deps)


def _verdict(report: SimulateReport) -> tuple[Decision, str]:
    combined = report.trace.combined
    return combined.decision, combined.reason


def test_superpowers_plan_is_denied_with_the_plans_directory(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _install(pack_repo)

    decision, reason = _verdict(_write(repo, deps(), "docs/superpowers/plans/x.md"))

    assert decision is Decision.DENY
    assert "docs/superpowers/plans/x.md" in reason
    assert "docs/plans/" in reason


def test_a_plan_in_the_plans_directory_passes(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _install(pack_repo)

    assert _verdict(_write(repo, deps(), "docs/plans/x.md"))[0] is Decision.NONE


@pytest.mark.parametrize(
    ("rel", "hint"),
    [
        ("docs/superpowers/specs/2026-01-02-login-design.md", "docs/specs/YYYY-MM-DD-<slug>.md"),
        (".scratch/login/spec.md", "docs/specs/YYYY-MM-DD-<slug>.md"),
        (".scratch/login/issues/01-form.md", "docs/plans/YYYY-MM-DD-<slug>.md"),
        ("docs/superpowers/notes.md", "Write specs to docs/specs/ and plans to docs/plans/."),
    ],
)
def test_misplaced_documents_name_their_directory(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], rel: str, hint: str
) -> None:
    repo = _install(pack_repo)

    decision, reason = _verdict(_write(repo, deps(), rel))

    assert decision is Decision.DENY
    assert hint in reason, reason


@pytest.mark.parametrize(
    "rel", [".scratch/proto/app.py", ".scratch/proto/map.md", "docs/specs/2026-01-02-x.md"]
)
def test_prototypes_and_layout_documents_pass(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], rel: str
) -> None:
    repo = _install(pack_repo)

    assert _verdict(_write(repo, deps(), rel))[0] is Decision.NONE


def test_a_configured_specs_directory_is_named_and_allowed(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _install(pack_repo, {"specs_dir": "specs", "plans_dir": "work/plans"})

    allowed = _verdict(_write(repo, deps(), "specs/x.md"))
    blocked = _verdict(_write(repo, deps(), "docs/superpowers/plans/x.md"))

    assert allowed[0] is Decision.NONE
    assert blocked[0] is Decision.DENY
    assert "work/plans/YYYY-MM-DD-<slug>.md" in blocked[1]


def test_a_layout_directory_inside_a_blocked_folder_passes(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _install(pack_repo, {"plans_dir": "docs/superpowers/plans"})

    assert _verdict(_write(repo, deps(), "docs/superpowers/plans/x.md"))[0] is Decision.NONE


def test_a_bash_redirect_into_a_framework_folder_is_denied(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _install(pack_repo)

    decision, reason = _verdict(_bash(repo, deps(), "echo '# plan' > docs/superpowers/plans/x.md"))

    assert decision is Decision.DENY
    assert "docs/plans/" in reason


def test_the_shipped_directories_and_fallbacks_are_the_d60_defaults() -> None:
    """The hook ships D60 (sync rewrites it, D71); the runtime cannot import config.layout."""
    handler = engine_hook(HOOK_ID).frontmatter.handler
    assert handler is not None
    expected = {
        "specs_dir": LAYOUT_DEFAULTS["specs"],
        "plans_dir": LAYOUT_DEFAULTS["plans"],
        "scratch_dir": LAYOUT_DEFAULTS["scratch"],
    }

    assert dict(DEFAULT_DIRS) == expected
    assert {key: handler.config[key] for key in expected} == expected


def test_blank_directories_fall_back_to_the_defaults(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _install(pack_repo, {"plans_dir": " ", "specs_dir": 3})

    decision, reason = _verdict(_write(repo, deps(), "docs/superpowers/plans/x.md"))

    assert decision is Decision.DENY
    assert "docs/plans/YYYY-MM-DD-<slug>.md" in reason


def test_folder_case_is_folded_on_darwin(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _install(pack_repo)

    report = _write(repo, deps(platform="darwin"), "Docs/Superpowers/Plans/x.md")

    assert _verdict(report)[0] is Decision.DENY
