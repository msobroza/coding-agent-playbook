"""What the layout adapter would rewrite, from a scratch render (D71), for ``playbook validate``.

``playbook validate`` reports the layout rewrites per file. It reports the list the
sync step itself returns (``sync._layout_outputs.FileRewrite``) for a render into a
throwaway directory, the one ``sync --check`` uses, so the report names exactly the
generated files sync rewrites: only the artifacts ``applies_if`` keeps, the
engine-generated outputs (``AGENTS.md``, ``guard_config.json``) included, after Jinja.
The repo itself is never written.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.adapters.claude_code.settings.managed_merge import SettingsMergeError
from coding_agent_playbook.generated_output.write_guard import UserOwnedFileError
from coding_agent_playbook.rendering.jinja import TemplateSecurityError
from coding_agent_playbook.sync._check_modes import _rendered_scratch
from coding_agent_playbook.sync._hook_outputs import HookPolicyError
from coding_agent_playbook.sync.pipeline import _previous_lockfile
from coding_agent_playbook.sync.render import SkillDescriptionOverflowError

if TYPE_CHECKING:
    from coding_agent_playbook.sync._layout_outputs import FileRewrite
    from coding_agent_playbook.validation.context import SyncContext

# The render failures ``sync.pipeline.execute`` reports instead of a traceback.
_RENDER_ERRORS: Final = (
    TemplateSecurityError,
    SkillDescriptionOverflowError,
    SettingsMergeError,
    UserOwnedFileError,
    HookPolicyError,
    OSError,
)


class LayoutPreviewError(Exception):
    """The scratch render behind the layout report failed; the message says why."""


def preview_layout_rewrites(ctx: SyncContext) -> list[FileRewrite]:
    """The rewrites ``playbook sync`` would make in ``ctx``'s repo, one entry per file.

    ``[]`` without rendering anything when the layout rewrites nothing (the default
    layout, no framework aliases). Raises :class:`LayoutPreviewError` when the
    render fails the way a sync would.

    Example::

        for rewrite in preview_layout_rewrites(ctx):
            print("\\n".join(rewrite.lines()))
    """
    if not ctx.config.layout_rewriter():
        return []
    try:
        with _rendered_scratch(ctx, _previous_lockfile(ctx)) as (_scratch, recorder):
            return list(recorder.layout_rewrites)
    except _RENDER_ERRORS as exc:
        raise LayoutPreviewError(
            f"layout rewrites not reported: rendering the sync output failed: {exc}"
        ) from exc
