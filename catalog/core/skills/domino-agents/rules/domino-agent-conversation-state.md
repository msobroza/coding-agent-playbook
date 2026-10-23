---
id: domino-agent-conversation-state
name: Domino agent conversation state
description: "Either drop the conversation id entirely or create it on the server and keep the history in a store outside process memory and App-local files."
version: 1
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
section: service
priority: 43
tags: [python, domino, agents]
---

# Domino agent conversation state

A conversation id that the server echoes or invents while no history reaches the agent promises a memory the agent does not have. Choose one of two shapes:

- **Stateless:** the API has no conversation id at all; each request stands alone.
- **Stateful:** the server creates the id (through an injected id factory), stores the message history under it, and passes the last `max_history` messages to each run (pydantic-ai `message_history`).

A stateful agent keeps that store outside process memory and outside files the App writes: an autoscaled App runs several pods that share neither, a viewer's requests can reach different pods without session affinity, and files an App writes at run time are lost when it stops.

## Bad Example

```python
class ChatResponse(BaseModel):
    response: str
    conversation_id: str


@router.post("/chat")
async def chat(body: ChatRequest, request: Request, ask: AskDep) -> ChatResponse:
    answer = await ask(body.message)  # no history reaches the agent
    conversation_id = body.conversation_id or str(id(request))
    return ChatResponse(response=answer["answer"], conversation_id=conversation_id)
```

## Good Example

A stateless API says so in its schema:

```python
class ChatResponse(BaseModel):
    response: str
```

A stateful one injects its store through `create_app`:

```python
class ConversationStore(Protocol):
    async def load(self, conversation_id: str, limit: int) -> list[ModelMessage]: ...

    async def append(self, conversation_id: str, messages: Sequence[ModelMessage]) -> None: ...


async def ask_in_conversation(
    agent: Agent[AgentDeps, str],
    store: ConversationStore,
    conversation_id: str,
    question: str,
    *,
    max_history: int,
) -> str:
    history = await store.load(conversation_id, limit=max_history)
    result = await agent.run(question, message_history=history)
    await store.append(conversation_id, result.new_messages())
    return result.output
```

## Notes

- Persistence and replica state are domino-app-external-persistence and domino-app-replica-state (domino-apps).
- A2A clients continue a conversation through the protocol's own context id.
- The agent example is stateless and its README says why.
- See examples/simple-agent-api/app/chat.py.
