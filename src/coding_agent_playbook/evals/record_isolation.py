"""The credentials an isolated ``playbook eval --run --record`` needs (#329 ticket 02).

A record run starts the harness and the LLM judge with an empty temporary config
directory, so no personal instructions, plugins, hooks or MCP servers reach a
measured run, and neither does the user's login. Each process therefore needs a
credential from the environment:

- on an endpoint (the target's, or ``[evals.judge] endpoint`` for the judge),
  that endpoint's token (``token_env``, or its ``token_command``);
- without one, :data:`API_KEY_VARIABLE`.

:func:`check_record_credentials` refuses before the first paid call when one is
missing, naming the variables, never a value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.model_pins import RecordRefusedError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evals.endpoints import Endpoint

#: The variable an isolated run without an endpoint reads its Anthropic API key from.
API_KEY_VARIABLE: Final = "ANTHROPIC_API_KEY"


def record_api_key(env: Mapping[str, str]) -> str:
    """The API key in ``env``; :class:`RecordRefusedError` naming the variable when unset or empty.

    Example::

        >>> record_api_key({"ANTHROPIC_API_KEY": "k0"})
        'k0'
    """
    key = env.get(API_KEY_VARIABLE, "")
    if not key:
        raise RecordRefusedError(
            f"--record runs isolated from your personal settings and login, so it needs "
            f"{API_KEY_VARIABLE} set; nothing was run"
        )
    return key


def check_record_credentials(
    *,
    target_endpoint: Endpoint | None,
    judge_endpoint: Endpoint | None,
    harness_isolated: bool,
    judge_isolated: bool,
    env: Mapping[str, str],
) -> None:
    """Raise :class:`RecordRefusedError` unless every isolated process has a credential in ``env``.

    ``harness_isolated`` and ``judge_isolated`` say which processes run isolated
    (a fake runner, or no judge, needs none). The message names
    :data:`API_KEY_VARIABLE` and the endpoint's ``token_env``.

    Example::

        >>> check_record_credentials(target_endpoint=None, judge_endpoint=None,
        ...     harness_isolated=True, judge_isolated=False, env={"ANTHROPIC_API_KEY": "k0"})
    """
    missing = [
        _missing_credential(role, endpoint, env)
        for role, endpoint, isolated in (
            ("the harness", target_endpoint, harness_isolated),
            ("the judge", judge_endpoint, judge_isolated),
        )
        if isolated
    ]
    problems = list(dict.fromkeys(problem for problem in missing if problem is not None))
    if problems:
        raise RecordRefusedError(
            "--record runs the harness and the judge isolated from your personal settings "
            "and login, so each needs a credential in the environment: "
            + "; ".join(problems)
            + f". Set {API_KEY_VARIABLE}, or the token_env of the endpoint; nothing was run"
        )


def _missing_credential(role: str, endpoint: Endpoint | None, env: Mapping[str, str]) -> str | None:
    """Why ``role`` has no credential in ``env``, or ``None`` when it has one."""
    if endpoint is None:
        if env.get(API_KEY_VARIABLE):
            return None
        return f"{role} runs on Anthropic's API and {API_KEY_VARIABLE} is unset or empty"
    if endpoint.token_command is not None:
        return None  # read when the route is built, still before any paid call
    if endpoint.token_env is None:
        return f"{role} runs on endpoint {endpoint.name!r}, which sets no token_env"
    if env.get(endpoint.token_env):
        return None
    return (
        f"{role} runs on endpoint {endpoint.name!r}, whose token_env "
        f"{endpoint.token_env} is unset or empty"
    )
