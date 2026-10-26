---
id: domino-agent-chat-endpoint
name: Domino agent chat endpoint
description: "Serve chat from one thin POST route with a bounded message and map the agent's own failures to 502 and 504 with fixed bodies."
scope: scoped
globs:
  - "**/app.sh"
  - "**/main.py"
  - "**/asgi.py"
  - "**/chat_app.py"
  - "**/*agent*.py"
  - "**/chat.py"
applies_if:
  domino_project: true
  has_framework: ["fastapi"]
section: service
priority: 41
tags: [python, domino, agents, fastapi]
---

# Domino agent chat endpoint

One POST route serves chat, and each production request passes through the traced request function. The route stays thin:

- the request model bounds `message` with `min_length=1` and a `max_length` constant, because every character costs model tokens;
- the route only awaits the traced request function, which it gets from a provider dependency reading `app.state`;
- the agent's own failures join the app's error table: provider HTTP errors, unexpected model output, an exceeded request limit and an unavailable token become 502, an exceeded run deadline 504, each with a fixed client-safe body;
- `responses=` documents 502 and 504 in OpenAPI.

An RPC-style `/chat` path is acceptable for an agent API; it is the one exception to web-api-resource-naming.

## Bad Example

```python
class ChatRequest(BaseModel):
    message: str  # unbounded
    conversation_id: str | None = None


@app.post("/chat")
async def chat(body: ChatRequest, request: Request) -> dict[str, str]:
    try:
        result = await ask_agent(body.message)
        return {"response": result, "conversation_id": str(id(request))}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))  # leaks internals
```

## Good Example

```python
MAX_MESSAGE_CHARS = 4000


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatResponse(BaseModel):
    response: str


def get_ask(request: Request) -> AskAgent:
    return request.app.state.ask


AskDep = Annotated[AskAgent, Depends(get_ask)]


@router.post("/chat", responses={502: {"model": ErrorBody}, 504: {"model": ErrorBody}})
async def chat(body: ChatRequest, ask: AskDep) -> ChatResponse:
    answer = await ask(body.message)
    return ChatResponse(response=answer["answer"])
```

```python
ERROR_TABLE: dict[type[Exception], tuple[int, str]] = {
    ModelHTTPError: (502, "The model provider failed; try again later."),
    UnexpectedModelBehavior: (502, "The model returned an unusable answer."),
    UsageLimitExceeded: (502, "The agent reached its request limit."),
    TokenUnavailableError: (502, "The model endpoint is unavailable."),
    asyncio.TimeoutError: (504, "The agent took too long to answer."),
}
```

## Notes

- Schemas, the error table, thin routes, providers and OpenAPI metadata are web-api-schemas, fastapi-error-boundaries, fastapi-thin-routes, fastapi-dependency-providers and fastapi-openapi-metadata (web-application).
- The run deadline sits below the App proxy's read timeout, 300 seconds by default (domino-agent-run-limits, domino-app-proxy-limits).
- A stateless agent has no conversation id at all (domino-agent-conversation-state).
- See examples/simple-agent-api/app/chat.py and examples/simple-agent-api/app/main.py.
