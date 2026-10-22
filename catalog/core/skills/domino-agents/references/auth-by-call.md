# Auth by call

A decision guide: which credential each outbound call of an agent uses, where
it comes from and how it is attached. Agents meet four answers to the same
question (a provider key, the rotating Domino access token, the API proxy, or
nothing), spread over this skill, domino-apps and domino-jobs. Find the call
target, then read the rules in its row.

## Decision table

| Call target | Credential | Comes from | Attached by | Rules |
| --- | --- | --- | --- | --- |
| External LLM provider | The provider's API key | A project or user environment variable, read once into settings | Passed explicitly to the provider when the model is built | domino-agent-llm-keys, domino-agent-settings |
| Domino-hosted, OpenAI-compatible model endpoint | The rotating Domino access token, a bearer token | The run's local access-token endpoint, through one async token provider with a timeout and a short cache | An httpx auth flow on one long-lived client, fresh on every call, retried once on a 401 | domino-agent-access-token, domino-agent-endpoint-auth |
| Restricted Domino model API endpoint | That endpoint's model access token | A setting fed by an environment variable | Basic auth for a synchronous endpoint, a Bearer header for an asynchronous one | domino-app-endpoint-auth (domino-apps) |
| Another Domino App or agent, over REST or A2A | The rotating Domino access token, a bearer token | The same shared token provider | The auth flow of one long-lived client, under a deadline | a2a-client-deadlines, domino-agent-endpoint-auth |
| The Domino platform API | None in agent code | The API proxy or python-domino | The proxy or the client library attaches the token itself | domino-api-proxy-auth (domino-jobs) |
| Local runs outside Domino | A provider key only | A local environment variable | As for an external provider; settings report the run is outside Domino, so no token provider is built and no Authorization header is sent | domino-agent-settings, domino-agent-access-token |

Token rotation and refresh are domino-agent-access-token; where each
credential is read and how it reaches its client is domino-agent-settings.

## What never carries a credential

| Place | Why it is public | Rule |
| --- | --- | --- |
| A traced function's parameters and return value | add_tracing records them; the Traces tab and evaluators read them back | domino-agent-redact-traces |
| Span outputs and evaluation results | Shown on the agent's dashboard | domino-agent-redact-traces |
| Logs | App logs are kept and can be shared with support | domino-agent-logging, domino-agent-redact-traces |
| The agent config file | DominoRun attaches it to the experiment run and the logged model | domino-agent-llm-keys, domino-agent-config-file |
| The agent card | Served to anyone who can reach the App | a2a-agent-card |

How a credential stays out of the traced function and out of printed settings
is domino-agent-redact-traces.

## Project or user variables

A key every collaborator may use goes into a project variable; a personal key
goes into a user variable and ties the run to that person. Which level to pick
is domino-secrets-in-env-vars (domino-jobs). An App runs with the user-level
variables of whoever last started it, so a restart by a colleague swaps the
keys: domino-app-starter-settings (domino-apps).

## Viewer identity belongs to domino-apps

The identity of the person using the App (the domino-username header, the
viewer JWT, a viewer's own token) is not an outbound credential of the agent.
Its rules are domino-app-viewer-identity, domino-app-verify-viewer-jwt and
domino-app-viewer-token (domino-apps). Never forward a viewer's token to a
model provider or another agent in place of the agent's own credential.
