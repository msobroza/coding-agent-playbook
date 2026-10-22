# Agent lifecycle on Domino

A decision guide: where each piece of an agent runs on Domino 6.2, from the
first workspace session to scored production traces, and which rule governs it.
It names rules by id; read the rule before you edit the code it covers.

## Stages and where they run

| Stage | Runs as | What happens | Rules |
| --- | --- | --- | --- |
| Develop | Workspace | Edit the agent, run it locally or as a preview, call the request function by hand; nothing here is a record. | domino-agent-app-factory, domino-agent-settings, domino-agent-config-file |
| Evaluate | Job | One evaluation script wraps every case in one DominoRun; each case calls the same traced request function the App uses, scored by inline evaluators. | domino-agent-dev-eval-job, domino-agent-evaluators, domino-agent-trace-entrypoint |
| Compare | Experiment Manager | Runs of the evaluation Job are compared by their agent config, summary metrics and traces. | domino-agent-config-file, domino-agent-dev-eval-job |
| Deploy | Deploy Agent | Started from the chosen Job-originated run (or from the Apps view) with the launch script as entrypoint; the agent is hosted as an App with its own dashboard. | domino-agent-app-factory |
| Serve | App hosting | The App builds the agent once; add_tracing on the one request function records every user request, with no evaluator attached. | domino-agent-app-factory, domino-agent-trace-entrypoint, domino-agent-eval-out-of-band |
| Monitor | Scheduled Job | A sequential schedule reads the agent's traces with search_agent_traces from a watermark and writes scores back with log_evaluation. | domino-agent-eval-out-of-band, domino-agent-prod-eval-watermark, domino-agent-evaluators |

The workspace is for iteration only: a result that matters (a metric, a
comparison, the run you deploy) comes from a Job, because only a Job's run
records the commit, the agent config and the traces together.

## Which run type for which piece of code

| Code | Runs as | Rules |
| --- | --- | --- |
| The app factory, chat route and A2A sub-app | App (deployed agent) | domino-agent-app-factory, plus domino-app-launch-script and domino-app-bind-host-port (domino-apps) |
| The development evaluation script | Job | domino-agent-dev-eval-job, plus domino-job-entry-point and domino-job-exit-codes (domino-jobs) |
| The production evaluation script | Scheduled Job, sequential | domino-agent-eval-out-of-band, plus domino-job-schedules and domino-idempotent-jobs (domino-jobs) |
| Evaluators | Inside either evaluation Job, never in the App's request path | domino-agent-evaluators |
| The watermark file | A dataset path read from the environment | domino-agent-prod-eval-watermark, plus domino-paths-from-env (domino-jobs) |
| Experiment names and run records | The evaluation Job's run | domino-agent-dev-eval-job, plus domino-mlflow-tracking (domino-jobs) |

A request never runs an evaluation; the evaluation Jobs call the same traced
request function the App serves, so development and production traces compare.

## SDK names by release

The 6.2 user guide and SDK reference do not always agree with newer material;
domino-agent-sdk-names keeps the SDK behind one seam so a rename touches one
module.

| Topic | On 6.2 | In newer material | Rule |
| --- | --- | --- | --- |
| Development evaluation wrapper | DominoRun | DominoAgentContext, a DominoRun subclass for runs that originate from an agent, already listed in the 6.2 SDK reference | domino-agent-sdk-names, domino-agent-dev-eval-job |
| Import path | domino.agents.tracing and domino.agents.logging | the same; the older domino.aisystems alias is not used | domino-agent-sdk-names |
| Summary-metric argument | custom_summary_metrics in the SDK reference | aggregated_metrics | domino-agent-sdk-names: check the installed signature |
| Production tracing | add_tracing alone, per the user guide | init_tracing, which needs DOMINO_AGENT_IS_PROD and DOMINO_APP_ID | domino-agent-trace-entrypoint |
| Deploy Agent | in the run's menu of the runs table on 6.2.0 | may move between releases | domino-agent-app-factory |

## Environment variables an agent meets

| Variable | Set by | Read by | Rule |
| --- | --- | --- | --- |
| DOMINO_API_HOST | Domino, inside runs | settings, as the in-Domino flag | domino-agent-settings |
| DOMINO_API_PROXY | Domino, inside runs | settings, for the access-token URL | domino-agent-settings, domino-agent-access-token |
| MLFLOW_TRACKING_URI | Domino, inside runs | the SDK; never set by the repo | domino-agent-settings |
| DOMINO_AGENT_CONFIG_PATH | the agent SDK's runtime | the SDK; never set by the repo | domino-agent-settings, domino-agent-config-file |
| DOMINO_AGENT_IS_PROD, DOMINO_APP_ID | the agent SDK's runtime | the SDK's init_tracing; never set by the repo | domino-agent-settings, domino-agent-trace-entrypoint |
| Provider keys (OPENAI_API_KEY and peers) | project or user variables | settings, passed to the provider | domino-agent-settings, domino-agent-llm-keys |
| DOMINO_DATASETS_DIR | Domino, inside runs | settings, for dataset paths such as the watermark | domino-paths-from-env (domino-jobs) |

Reserved names and the repo's own prefix are domino-env-var-names (domino-jobs).

## Where the example implements each stage

Domino repos get the example app examples/simple-agent-api; its files map to
the stages above:

- Develop: app/settings.py, agent_config.yaml, app/llm.py, app/agent.py.
- Evaluate: evals/dev_eval.py, evals/evaluators.py, sample_questions.csv.
- Deploy and serve: app.sh, app/asgi.py, app/main.py, app/chat.py, app/a2a.py,
  app/tracing.py.
- Monitor: evals/prod_eval.py, evals/trace_store.py.
- Tests for every stage, on fakes: tests/.
