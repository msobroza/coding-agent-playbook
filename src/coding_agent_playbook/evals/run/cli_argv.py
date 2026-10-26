"""The argv a harness or judge CLI is spawned with: a command template, the prompt and the model.

The Claude Code and OpenCode runners and the LLM judge all take a configurable
arg-list template with an optional ``{prompt}`` token. One function builds the
argv for all three, so the prompt interpolation and the ``--model`` flag of an
Eval target are spelled once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Placeholder token in a command template, replaced by the prompt.
PROMPT_TOKEN: Final = "{prompt}"

#: The flag both the ``claude`` and the ``opencode run`` CLIs take a model id with.
MODEL_FLAG: Final = "--model"


def build_cli_argv(command: Sequence[str], prompt: str, model: str | None = None) -> list[str]:
    """``command`` with ``prompt`` interpolated, then ``--model <model>`` when a model is set.

    Each ``{prompt}`` token is replaced by the prompt; a template without one gets
    the prompt appended as its last argument. The model is appended verbatim (an
    Eval target's model is sent to the harness exactly as written); both CLIs
    accept options after the positional prompt.

    Example::

        >>> build_cli_argv(("claude", "-p", "{prompt}"), "hi", "claude-opus-5-5")
        ['claude', '-p', 'hi', '--model', 'claude-opus-5-5']
        >>> build_cli_argv(("opencode", "run"), "hi")
        ['opencode', 'run', 'hi']
    """
    if any(PROMPT_TOKEN in part for part in command):
        argv = [part.replace(PROMPT_TOKEN, prompt) for part in command]
    else:
        argv = [*command, prompt]
    if model is not None:
        argv += [MODEL_FLAG, model]
    return argv
