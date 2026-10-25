---
id: domino-agent-endpoint-auth
name: Domino agent model endpoint auth
description: "Attach the rotating token to a Domino-hosted model endpoint through an httpx auth flow on one long-lived client, retrying once on a 401."
scope: scoped
globs:
  - "**/settings.py"
  - "**/config.py"
  - "**/*token*.py"
  - "**/*auth*.py"
  - "**/llm.py"
  - "**/*agent*.py"
applies_if:
  domino_project: true
section: secrets
priority: 22
tags: [python, domino, agents, security, httpx]
---

# Domino agent model endpoint auth

A Domino-hosted, OpenAI-compatible model endpoint takes a bearer token that rotates every few minutes. The model client for it is one `httpx.AsyncClient` with timeouts from settings, built by `create_app` and closed after the lifespan's `yield`. An `httpx.Auth` subclass implements `async_auth_flow`: it awaits the token provider (domino-agent-access-token), sets `Authorization: Bearer ...`, and on a 401 calls `invalidate()` and sends the request once more.

The OpenAI-compatible provider receives this client, and the model name comes from the agent config, never an empty string. The agent is never rebuilt to rotate a token: the client attaches a fresh one on every call.

## Bad Example

```python
async def answer(question: str) -> str:
    # A new agent per request, a blocking token fetch, and an empty model name.
    token = requests.get(token_url).text
    provider = OpenAIProvider(base_url=endpoint_url, api_key=token)
    agent = Agent(OpenAIChatModel("", provider=provider))
    result = await agent.run(question)
    return result.output
```

## Good Example

```python
class DominoTokenAuth(httpx.Auth):
    def __init__(self, tokens: AccessTokenProvider) -> None:
        self._tokens = tokens

    def sync_auth_flow(self, request: httpx.Request) -> Iterator[httpx.Request]:
        raise RuntimeError("DominoTokenAuth works only with httpx.AsyncClient")

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        request.headers["Authorization"] = f"Bearer {await self._tokens.token()}"
        response = yield request
        if response.status_code == 401:
            self._tokens.invalidate()
            request.headers["Authorization"] = f"Bearer {await self._tokens.token()}"
            yield request


def build_model(
    config: AgentConfig, settings: AgentSettings, client: httpx.AsyncClient
) -> OpenAIChatModel:
    provider = OpenAIProvider(base_url=str(settings.endpoint_base_url), http_client=client)
    return OpenAIChatModel(config.model.name, provider=provider)
```

`create_app` builds the client once, `httpx.AsyncClient(auth=DominoTokenAuth(tokens), timeout=...)`, and the lifespan closes it.

## Notes

- Client lifetime is httpx-shared-client (where the repo declares FastAPI and httpx) and blocking calls are fastapi-no-blocking-calls (where it uses FastAPI), both in web-application.
- Restricted Domino model API endpoints use the scheme their mode expects (domino-app-endpoint-auth, domino-apps).
- The 6.2 deploy page's sample builds the agent inside the traced function on every call; build it once instead.
- See examples/simple-agent-api/app/domino_token.py and examples/simple-agent-api/app/llm.py.
