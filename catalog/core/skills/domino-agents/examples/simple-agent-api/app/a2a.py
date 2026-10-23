# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""The A2A sub-app: one agent card, and conversations bounded by the config's max_history.

build_a2a_app is called by create_app, never at import. The card's skills match
the agent's two tools, its version follows the agent config, and its URL is the
published App URL plus ``/a2a`` from settings (the library default points at
localhost). The default broker and task storage live in this process's memory, so
the App runs one worker on one pod.
"""

from collections.abc import Sequence
from typing import Final

from fasta2a.pydantic_ai import agent_to_a2a
from fasta2a.schema import AgentProvider, Skill
from fasta2a.storage import InMemoryStorage
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from starlette.applications import Starlette

from app.agent import PHILOSOPHY_TOOL, SCIENCE_TOOL
from app.settings import AgentConfig, AgentSettings

#: The mount path of the A2A sub-app under the App.
A2A_PATH: Final = "/a2a"
AGENT_NAME: Final = "Line Agent"
AGENT_DESCRIPTION: Final = (
    "Answers any question with one short line: a science line for science questions, "
    "a philosophy line for everything else."
)
CARD_SKILLS: Final = (
    Skill(
        id=SCIENCE_TOOL,
        name="Science line",
        description="Answers a science question with one short line about science.",
        tags=["science", "lines"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    ),
    Skill(
        id=PHILOSOPHY_TOOL,
        name="Philosophy line",
        description="Answers any other question with one short line of philosophy.",
        tags=["philosophy", "lines"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    ),
)


def _starts_a_turn(message: ModelMessage) -> bool:
    """True for a request that carries the user's prompt (not a tool return)."""
    return isinstance(message, ModelRequest) and any(
        isinstance(part, UserPromptPart) for part in message.parts
    )


def trim_history(messages: Sequence[ModelMessage], limit: int) -> list[ModelMessage]:
    """The last ``limit`` messages, starting at a user turn so no tool call loses its return."""
    kept = list(messages[-limit:]) if limit > 0 else []
    while kept and not _starts_a_turn(kept[0]):
        kept.pop(0)
    return kept


class BoundedContextStorage(InMemoryStorage):
    """In-memory A2A storage that hands the agent at most ``max_messages`` of a conversation."""

    def __init__(self, max_messages: int) -> None:
        super().__init__()
        self._max_messages = max_messages

    async def load_context(self, context_id: str) -> list[ModelMessage] | None:
        context = await super().load_context(context_id)
        return None if context is None else trim_history(context, self._max_messages)


def card_url(settings: AgentSettings) -> str:
    """The URL the card publishes: the App URL plus the mount path."""
    return f"{str(settings.public_url).rstrip('/')}{A2A_PATH}"


def build_a2a_app(
    agent: Agent[None, str], config: AgentConfig, settings: AgentSettings
) -> Starlette:
    """The A2A app for ``agent``; create_app mounts it and runs its lifespan."""
    a2a_app: Starlette = agent_to_a2a(
        agent,
        storage=BoundedContextStorage(config.agent.max_history),
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        version=config.version,
        url=card_url(settings),
        provider=AgentProvider(
            organization=settings.provider_organization, url=str(settings.provider_url)
        ),
        skills=list(CARD_SKILLS),
    )
    return a2a_app
