# simple-agent-api

An LLM agent served as a Domino App. It answers any question with one short line: a science line when the question is about science, a philosophy line for anything else, each picked by a tool the model calls. It speaks two protocols from one process: a REST chat route and the Agent2Agent (A2A) protocol. Two evaluation Jobs measure it: a development evaluation before deployment and a scheduled production evaluation after.

This is Domino Data Lab's "REST + A2A" agent example, `simple_agent_api_only`, adapted so that every file follows the domino-agents rules. Its license is Apache-2.0; the license text is in references/LICENSE.simple-agent-api of this skill, and every adapted file opens with a one-line change notice.

## Contents

- [Layout](#layout)
- [Run it](#run-it)
- [One request, end to end](#one-request-end-to-end)
- [Calling the API from another Domino run](#calling-the-api-from-another-domino-run)
- [Tracing and evaluation](#tracing-and-evaluation)
- [Tests](#tests)
- [Which file shows which rule](#which-file-shows-which-rule)
- [What changed from upstream](#what-changed-from-upstream)

## Layout

```text
simple-agent-api/
├── app.sh                 launch script: the App's and Deploy Agent's entrypoint
├── agent_config.yaml      the agent's non-secret choices, logged with every evaluation run
├── sample_questions.csv   labelled development questions
├── pyproject.toml         dependencies, the optional `domino` extra, pytest, ruff, mypy
├── app/                   the App
│   ├── asgi.py            the only module that reads the environment
│   ├── main.py            create_app: the composition root and the error table
│   ├── settings.py        AgentSettings (environment) and AgentConfig (the YAML file)
│   ├── agent.py           the tools, build_agent and the traced request function
│   ├── llm.py             the chat model from the config and the settings
│   ├── domino_token.py    the rotating Domino token and its httpx auth flow
│   ├── chat.py            POST /chat
│   ├── a2a.py             the A2A sub-app and its agent card
│   ├── tracing.py         the seam in front of the Domino agent SDK
│   └── logs.py            JSON-lines logging on stdout
├── evals/                 the Jobs
│   ├── evaluators.py      pure scorers shared by both Jobs
│   ├── dev_eval.py        development evaluation inside DominoRun
│   ├── prod_eval.py       scheduled production evaluation with a watermark
│   └── trace_store.py     the seam in front of the SDK's trace search
└── tests/                 fakes for the model, the token endpoint and the SDK
```

## Run it

Locally, with an OpenAI key and no Domino:

```bash
export OPENAI_API_KEY=...            # the provider key; never in agent_config.yaml
export SIMPLE_AGENT_LOG_LEVEL=INFO
uv run uvicorn app.asgi:app --port 8888
```

Outside Domino the token provider is off (no Authorization header is sent to a model endpoint) and tracing is off with one warning.

As a Domino App: publish the project with `app.sh` as the launch script. Set `OPENAI_API_KEY` as a project environment variable, and `SIMPLE_AGENT_PUBLIC_URL` to the App's published URL once it is known, so the A2A card points callers to it. Keep the App at one pod (maximum pods 1): the A2A tasks live in the memory of the one process.

To use a model hosted on a Domino endpoint instead, set `provider: domino-endpoint` in `agent_config.yaml` and `SIMPLE_AGENT_ENDPOINT_BASE_URL` to the endpoint's OpenAI-compatible base URL; the App then fetches the run's rotating access token (from `DOMINO_API_PROXY`, else the local proxy on port 8899) and attaches it to every model request.

As a Domino Agent:

1. Run the development evaluation as a Job from the project root: `python -m evals.dev_eval sample_questions.csv`. Its run carries the commit, `agent_config.yaml`, the traces and the summary metrics.
2. Compare runs in Experiment Manager.
3. Deploy Agent from the chosen run, with `app.sh` as the entrypoint. On 6.2.0 Deploy Agent sits in the run's menu of the runs table.

The production evaluation is a scheduled Job, set to run sequentially so two runs never overlap:

```bash
python -m evals.prod_eval --agent-id <agent id> --agent-version <version>
```

It needs `SIMPLE_AGENT_WATERMARK_PATH`, a file on a dataset path, where it keeps the end of the last scored window.

## One request, end to end

1. `app.sh` execs one uvicorn process on `0.0.0.0:8888` serving `app.asgi:app`.
2. `app/asgi.py` builds `AgentSettings()` from the environment, configures logging and calls `create_app(settings)`.
3. `create_app` loads `agent_config.yaml`, builds the HTTP clients with timeouts, the model, the agent with its two tools, the traced `ask_agent` and the A2A sub-app, and mounts `/a2a`. Nothing of this happens at import.
4. `POST /chat` validates the body (`message`, 1 to 4000 characters, no other field) and awaits `ask_agent(question)`.
5. `ask_agent` runs the agent under a request limit and a deadline from the config. The model calls one tool, the tool returns a line, the model repeats it.
6. For a Domino endpoint, each model request passes through `DominoTokenAuth`, which sets the cached token and, on a 401, refreshes it and resends once.
7. The route returns `{"response": "..."}`.

The agent's own failures have fixed answers: a body that breaks the schema is 422; a provider error, an unusable model answer, an exceeded request limit or an unavailable token is 502; a run past its deadline is 504. Anything else is a 500. No error body carries exception text.

## Calling the API from another Domino run

A caller inside Domino authenticates with its own run's token, with a timeout on both calls, and never prints the token:

```bash
token="$(curl --silent --max-time 5 http://localhost:8899/access-token)"
curl --silent --max-time 130 \
  -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" \
  -d '{"message": "What is the mass of planet earth?"}' \
  https://domino.example.com/apps/simple-agent/chat
```

Other agents use A2A at the App URL plus `/a2a/` and read the card at `/a2a/.well-known/agent-card.json`; they continue a conversation through the protocol's context id, and the agent sees at most `max_history` messages of it.

## Tracing and evaluation

The request function is `ask_agent(question: str) -> {"answer": str, "tools": list[str]}`, traced under the span name `ask_agent` (`REQUEST_SPAN_NAME`). That name, the parameter name and the two keys are a contract: the evaluators and the production Job read them, so change them together.

The development evaluation runs every row of `sample_questions.csv` inside one `DominoRun`. Each row goes through `run_case(question_id, question, expected_tool)`, traced as `dev_eval_case` with `dev_span_evaluator`, which calls the same traced `ask_agent` the App serves. The evaluator scores `answered`, `single_tool`, `answer_chars` and, from the row's label, `tool_match`. Cases run one after another; a case that raises is logged with its id, and the Job exits 1 when any case failed. The questions include off-topic rows and one prompt-injection attempt.

The production evaluation fixes its window end when it starts, begins `SIMPLE_AGENT_TRACE_OVERLAP_SECONDS` (at least the run deadline) before the stored watermark, or `SIMPLE_AGENT_LOOKBACK_HOURS` back on the first run, and pages through `search_agent_traces` until no page token comes back. It reads the `ask_agent` span of each trace, skips traces that already hold its metrics, logs `answered`, `single_tool` and `answer_chars` with `log_evaluation`, and writes the new watermark atomically only after every page succeeded. A corrupt watermark file stops the Job with its path.

User questions and answers are recorded in traces by design; nothing secret is: the token and the provider key never reach a traced parameter or return value, and the logs carry sizes, tool names and latencies, not the conversation.

## Tests

```bash
uv run pytest
uv run mypy
```

The suite needs no Domino, no provider key and no network. `tests/conftest.py` switches real model requests off and builds settings in code; `tests/fakes.py` holds a scripted model that picks a tool by keyword, a token provider with numbered tokens, a recording tracer that stands in for `add_tracing` and `DominoRun`, and a trace store that serves pages with page tokens. The token tests run against an `httpx.MockTransport` endpoint and a fake clock. The `domino` extra is never installed in CI, so the one test of the real SDK adapter is skipped there.

## Which file shows which rule

Rules of other skills carry their skill name in parentheses.

| File | Rules |
| --- | --- |
| app.sh | domino-agent-app-factory, domino-agent-logging, a2a-mount-lifespan, domino-app-bind-host-port (domino-apps), domino-app-launch-script (domino-apps), domino-app-logging (domino-apps) |
| agent_config.yaml | domino-agent-config-file, domino-agent-llm-keys, domino-agent-run-limits |
| sample_questions.csv | domino-agent-dev-eval-job, domino-agent-evaluators |
| pyproject.toml | domino-agent-sdk-names, python-pyproject-dependencies (python-tooling), pytest-configuration (python-tooling) |
| app/settings.py | domino-agent-settings, domino-agent-config-file, domino-agent-llm-keys, domino-env-var-names (domino-jobs), domino-secrets-in-env-vars (domino-jobs), pydantic-typed-settings (python-coding), pydantic-special-types (python-coding) |
| app/logs.py | domino-agent-logging, domino-agent-redact-traces, domino-app-logging (domino-apps), domino-job-logging (domino-jobs) |
| app/domino_token.py | domino-agent-access-token, domino-agent-endpoint-auth, python-retries-and-timeouts (python-coding), python-protocols (python-coding), python-custom-exceptions (python-coding) |
| app/llm.py | domino-agent-endpoint-auth, domino-agent-llm-keys, httpx-shared-client (web-application), python-dependency-injection (python-coding) |
| app/agent.py | domino-agent-trace-entrypoint, domino-agent-run-limits, domino-agent-redact-traces, domino-agent-config-file, python-pure-core (python-coding) |
| app/tracing.py | domino-agent-sdk-names, domino-agent-trace-entrypoint, design-adapter (design-patterns), python-protocols (python-coding) |
| app/chat.py | domino-agent-chat-endpoint, domino-agent-conversation-state, web-api-schemas (web-application), fastapi-thin-routes (web-application), fastapi-dependency-providers (web-application), pydantic-field-constraints (python-coding) |
| app/a2a.py | a2a-agent-card, a2a-mount-lifespan, domino-agent-config-file |
| app/main.py | domino-agent-app-factory, domino-agent-chat-endpoint, a2a-mount-lifespan, domino-app-relative-urls (domino-apps), fastapi-app-wiring (web-application), fastapi-error-boundaries (web-application), web-cors-origins (web-application), httpx-shared-client (web-application) |
| app/asgi.py | domino-agent-app-factory, domino-agent-logging, fastapi-app-wiring (web-application) |
| evals/evaluators.py | domino-agent-evaluators, python-pure-core (python-coding) |
| evals/trace_store.py | domino-agent-prod-eval-watermark, domino-agent-sdk-names, design-adapter (design-patterns) |
| evals/dev_eval.py | domino-agent-dev-eval-job, domino-agent-trace-entrypoint, domino-agent-run-limits, domino-job-entry-point (domino-jobs), domino-job-exit-codes (domino-jobs) |
| evals/prod_eval.py | domino-agent-prod-eval-watermark, domino-agent-eval-out-of-band, domino-agent-evaluators, domino-idempotent-jobs (domino-jobs), domino-run-scoped-writes (domino-jobs), domino-job-entry-point (domino-jobs) |
| tests/conftest.py | domino-agent-fake-llm-tests, pytest-fixtures (python-testing), pytest-conftest (python-testing) |
| tests/fakes.py | domino-agent-fake-llm-tests, domino-agent-fake-domino-tests, pytest-test-doubles (python-testing) |
| tests/test_api.py | domino-agent-chat-endpoint, domino-agent-trace-entrypoint, a2a-mount-lifespan, a2a-agent-card, a2a-client-deadlines |
| tests/test_agent.py | domino-agent-fake-llm-tests, domino-agent-run-limits, domino-agent-config-file, pytest-deterministic-tests (python-testing) |
| tests/test_domino_token.py | domino-agent-fake-domino-tests, domino-agent-access-token, domino-agent-endpoint-auth, domino-agent-redact-traces |
| tests/test_evals.py | domino-agent-evaluators, domino-agent-prod-eval-watermark, domino-agent-dev-eval-job, domino-agent-fake-domino-tests, pytest-parametrize-ids (python-testing) |

## What changed from upstream

- Typed settings from the environment replace scattered environment reads and hard-coded agent ids, token URLs and dataset paths.
- `create_app(settings)` and `asgi.py` replace the agent, the A2A app and the FastAPI app built at import.
- CORS comes from an explicit allow-list without credentials, off by default, instead of every origin with credentials.
- The chat route is thin and stateless: the invented conversation id is gone, the message is bounded, and failures map to 502 and 504 with fixed bodies instead of a 500 carrying the exception text.
- The Domino token is fetched asynchronously with a timeout, cached, shared under a lock and attached by an httpx auth flow, instead of a blocking call on every model request.
- The model name comes from the config (upstream passed an empty name), the provider key reaches the provider explicitly, and temperature and max tokens are sent instead of only logged.
- Each run has a request limit and a deadline from the config, and `max_history` bounds A2A conversations.
- The agent SDK sits behind one tracer seam and one trace-store seam; the framework's own instrumentation is not stacked on autologging.
- JSON-lines logging set up by each entry point replaces DEBUG logging at import and print banners; the launch script execs uvicorn without `--debug`.
- The evaluators are pure and deterministic instead of random scores, the development Job exits 1 on a failed case, and the production Job pages through every trace, skips scored ones, reads no private framework field and advances its watermark atomically only after success.
- The A2A card points to the published App URL and names a placeholder organization; the tools are named science_line and philosophy_line and return invented lines, so no real person is quoted.
- pydantic-ai is held below 2 and the A2A app is built with fasta2a's own pydantic-ai bridge, which replaces the deprecated `agent.to_a2a()`.
- Tests with a fake model and fakes of the Domino SDK are new.

Left out: the browser playground UI and its screenshots, the `.gitignore`, the README's call samples and registry recipe, the random evaluation library, and the quote lists.
