# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""The chat route: a bounded message in, the agent's answer out.

The route only awaits the traced request function, which a provider dependency
reads from app.state; the agent's failures reach the app's error table in
app/main.py. The API is stateless on purpose: there is no conversation id, because
no history reaches the agent between requests. The RPC-style ``/chat`` path is the
agent API's one exception to resource naming.
"""

from typing import Annotated, Final, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.agent import AskAgent

#: Every character of a message costs model tokens.
MAX_MESSAGE_CHARS: Final = 4000


class ChatRequest(BaseModel):
    """One question for the agent."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatResponse(BaseModel):
    """The agent's answer."""

    response: str


class ErrorBody(BaseModel):
    """A fixed, client-safe error message."""

    detail: str


def get_ask(request: Request) -> AskAgent:
    """The traced request function create_app stored on app.state."""
    return cast("AskAgent", request.app.state.ask)


AskDep = Annotated[AskAgent, Depends(get_ask)]

router = APIRouter()


@router.post(
    "/chat",
    summary="Ask the agent one question",
    responses={
        502: {"model": ErrorBody, "description": "The model or its endpoint failed."},
        504: {"model": ErrorBody, "description": "The agent did not answer in time."},
    },
)
async def chat(body: ChatRequest, ask: AskDep) -> ChatResponse:
    answer = await ask(body.message)
    return ChatResponse(response=answer["answer"])
