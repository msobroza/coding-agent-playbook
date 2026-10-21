# prU: target tree of catalog/core

Generated from the verified mapping data; do not edit by hand. Decisions: [../prU-core-python-skills.md](../prU-core-python-skills.md). `rules/` is flat on disk: the `# Section [IMPACT]` lines show how the generated index groups the rules, in priority order. `.md.j2` marks a Jinja template.

```text
catalog/core/
├── ATTRIBUTIONS.md                 # mapping table per source (D31)
├── rules/
│   └── always/
│       ├── 00-project-context.md.j2
│       └── 10-python-house-style.md
└── skills/
    ├── playbook-guardrails/
    │   └── SKILL.md                 # unchanged (generated from hooks)
    ├── python-coding/   # 48 rules, 9 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Error handling [CRITICAL]
    │   │   ├── python-error-handling.md
    │   │   ├── python-error-messages-with-context.md
    │   │   ├── python-error-boundaries.md
    │   │   ├── python-custom-exceptions.md
    │   │   │ # Code shape [HIGH]
    │   │   ├── python-small-units.md
    │   │   ├── python-early-return.md
    │   │   │ # Names, types, docs [HIGH]
    │   │   ├── python-meaningful-names.md
    │   │   ├── python-typing.md.j2
    │   │   ├── python-docstrings.md
    │   │   ├── python-comments-why.md
    │   │   ├── python-abstract-inputs.md
    │   │   ├── python-type-aliases.md
    │   │   │ # Effects and resources [HIGH]
    │   │   ├── python-dependency-injection.md
    │   │   ├── python-pure-core.md
    │   │   ├── python-no-global-singletons.md
    │   │   ├── python-context-managers.md
    │   │   ├── python-parameterized-queries.md
    │   │   ├── python-retries-and-timeouts.md
    │   │   ├── python-custom-context-managers.md
    │   │   │ # Asyncio [HIGH]
    │   │   ├── python-async.md.j2
    │   │   ├── python-async-tasks.md.j2
    │   │   ├── python-async-fanout.md.j2
    │   │   ├── python-async-generators.md
    │   │   │ # Pydantic validation [HIGH]
    │   │   ├── pydantic-boundaries.md
    │   │   ├── pydantic-field-constraints.md
    │   │   ├── pydantic-typed-settings.md
    │   │   ├── pydantic-model-validators.md
    │   │   ├── pydantic-special-types.md
    │   │   ├── pydantic-serializers.md
    │   │   │ # Classes and data shapes [MEDIUM]
    │   │   ├── python-data-shapes.md
    │   │   ├── python-protocols.md
    │   │   ├── python-properties.md
    │   │   ├── python-frozen-dataclasses.md
    │   │   ├── python-enums.md
    │   │   ├── python-dataclass-post-init.md
    │   │   ├── python-hide-internal-state.md
    │   │   │ # Control flow [MEDIUM]
    │   │   ├── python-match-fallback.md
    │   │   ├── python-function-signatures.md
    │   │   ├── python-match-destructuring.md
    │   │   ├── python-closures-and-partial.md
    │   │   ├── python-decorators.md
    │   │   │ # Idioms and performance [MEDIUM]
    │   │   ├── python-idioms.md
    │   │   ├── python-imports.md
    │   │   ├── python-collection-choice.md
    │   │   ├── python-optional-keys.md
    │   │   ├── python-comprehensions.md
    │   │   ├── python-generators.md
    │   │   └── python-str-join.md
    │   └── references/
    │       ├── LICENSE.python-best-practices
    │       ├── LICENSE.python-clean-architecture
    │       ├── choosing-a-data-shape.md
    │       ├── error-flow.md
    │       └── python-version-idioms.md
    ├── python-testing/   # 19 rules, 6 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Mocking [CRITICAL]
    │   │   ├── pytest-test-doubles.md.j2
    │   │   ├── pytest-autospec.md.j2
    │   │   │ # Test Structure [HIGH]
    │   │   ├── pytest.md.j2
    │   │   ├── pytest-first-properties.md
    │   │   ├── pytest-arrange-act-assert.md
    │   │   ├── pytest-one-behavior.md
    │   │   ├── pytest-no-test-logic.md
    │   │   ├── pytest-assertions.md
    │   │   │ # Test Isolation [HIGH]
    │   │   ├── pytest-deterministic-tests.md
    │   │   ├── pytest-monkeypatch.md
    │   │   │ # Fixtures [HIGH]
    │   │   ├── pytest-fixtures.md.j2
    │   │   ├── pytest-conftest.md.j2
    │   │   ├── pytest-factory-fixtures.md
    │   │   │ # Parametrization [MEDIUM]
    │   │   ├── pytest-parametrize.md
    │   │   ├── pytest-parametrize-ids.md
    │   │   │ # Coverage [MEDIUM]
    │   │   ├── pytest-edge-cases.md
    │   │   ├── pytest-branch-coverage.md
    │   │   ├── pytest-hypothesis-properties.md
    │   │   └── pytest-hypothesis-stateful.md
    │   └── references/
    │       ├── LICENSE.python-best-practices
    │       ├── LICENSE.python-clean-architecture
    │       ├── async-tests.md
    │       ├── choosing-a-test-double.md
    │       └── reviewing-tests.md
    ├── python-tooling/   # 7 rules, 5 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Linting [CRITICAL]
    │   │   ├── python-static-checks.md
    │   │   ├── ruff-lint.md
    │   │   │ # Type checking [HIGH]
    │   │   ├── mypy-type-checking.md
    │   │   │ # Formatting [HIGH]
    │   │   ├── ruff-format.md
    │   │   │ # Test configuration [HIGH]
    │   │   ├── pytest-configuration.md
    │   │   │ # Package management [MEDIUM]
    │   │   ├── python-uv-workflow.md
    │   │   └── python-pyproject-dependencies.md
    │   └── references/
    │       ├── LICENSE.python-best-practices
    │       ├── LICENSE.python-clean-architecture
    │       ├── check-failures.md
    │       └── uv-dependency-failures.md
    ├── ml-data/   # 15 rules, 8 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Serialization Security [CRITICAL]
    │   │   ├── ml-serialization-security.md.j2
    │   │   │ # Vectorization [CRITICAL]
    │   │   ├── ml-vectorization.md.j2
    │   │   ├── ml-build-once.md.j2
    │   │   │ # Indexing & Mutation [CRITICAL]
    │   │   ├── ml-data-transforms.md.j2
    │   │   ├── ml-loc-assignment.md
    │   │   │ # Dtypes & validation [HIGH]
    │   │   ├── ml-dtypes-at-load.md.j2
    │   │   ├── ml-check-after-load.md.j2
    │   │   ├── ml-frame-validation.md.j2
    │   │   ├── ml-numpy-dtypes.md
    │   │   ├── ml-categorical-labels.md.j2
    │   │   │ # Reproducibility [HIGH]
    │   │   ├── ml-seeded-randomness.md.j2
    │   │   │ # Chaining style [MEDIUM]
    │   │   ├── ml-method-chaining.md.j2
    │   │   ├── ml-named-aggregation.md.j2
    │   │   │ # Typing [MEDIUM]
    │   │   ├── ml-array-typing.md.j2
    │   │   │ # Testing [MEDIUM]
    │   │   └── ml-numeric-assertions.md.j2
    │   └── references/
    │       ├── LICENSE.python-best-practices
    │       ├── library-equivalents.md
    │       └── review-signals.md
    ├── web-application/   # 26 rules, 8 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Security [CRITICAL]
    │   │   ├── web-object-authorization.md
    │   │   ├── web-jwt-validation.md
    │   │   ├── web-password-hashing.md
    │   │   ├── web-secure-tokens.md
    │   │   ├── web-cors-origins.md
    │   │   │ # Database [CRITICAL]
    │   │   ├── sqlalchemy-bound-parameters.md
    │   │   ├── sqlalchemy-session-per-request.md
    │   │   ├── sqlalchemy-transaction-boundary.md.j2
    │   │   ├── sqlalchemy-eager-loading.md
    │   │   ├── alembic-migrations.md
    │   │   ├── sqlalchemy-2-style.md.j2
    │   │   │ # Async I/O [CRITICAL]
    │   │   ├── fastapi-no-blocking-calls.md
    │   │   ├── httpx-shared-client.md
    │   │   │ # API design [HIGH]
    │   │   ├── web-api-schemas.md.j2
    │   │   ├── fastapi-error-boundaries.md
    │   │   ├── web-api-pagination.md
    │   │   ├── web-http-methods.md
    │   │   │ # App structure [HIGH]
    │   │   ├── fastapi-app-wiring.md
    │   │   ├── fastapi-dependency-providers.md
    │   │   ├── fastapi-thin-routes.md
    │   │   │ # Observability [MEDIUM]
    │   │   ├── fastapi-request-id-logging.md
    │   │   │ # Testing [MEDIUM]
    │   │   ├── fastapi-dependency-overrides.md.j2
    │   │   ├── sqlalchemy-test-rollback.md.j2
    │   │   │ # API conventions [MEDIUM]
    │   │   ├── fastapi-query-parameters.md
    │   │   ├── web-api-resource-naming.md
    │   │   └── fastapi-openapi-metadata.md
    │   ├── references/
    │   │   ├── LICENSE.python-best-practices
    │   │   ├── LICENSE.python-clean-architecture
    │   │   ├── add-an-endpoint.md
    │   │   ├── api-review-checklist.md
    │   │   └── request-lifecycle.md
    │   └── examples/
    │       ├── fastapi-hotel-api/README.md
    │       ├── fastapi-hotel-api/pyproject.toml
    │       ├── fastapi-hotel-api/app/settings.py
    │       ├── fastapi-hotel-api/app/main.py
    │       ├── fastapi-hotel-api/app/asgi.py
    │       ├── fastapi-hotel-api/app/deps.py
    │       ├── fastapi-hotel-api/app/domain/model.py
    │       ├── fastapi-hotel-api/app/domain/errors.py
    │       ├── fastapi-hotel-api/app/operations/ports.py
    │       ├── fastapi-hotel-api/app/operations/room.py
    │       ├── fastapi-hotel-api/app/operations/customer.py
    │       ├── fastapi-hotel-api/app/operations/booking.py
    │       ├── fastapi-hotel-api/app/db/models.py
    │       ├── fastapi-hotel-api/app/db/repositories.py
    │       ├── fastapi-hotel-api/app/routers/schemas.py
    │       ├── fastapi-hotel-api/app/routers/rooms.py
    │       ├── fastapi-hotel-api/app/routers/customers.py
    │       ├── fastapi-hotel-api/app/routers/bookings.py
    │       ├── fastapi-hotel-api/tests/conftest.py
    │       ├── fastapi-hotel-api/tests/fakes.py
    │       ├── fastapi-hotel-api/tests/test_operations.py
    │       ├── fastapi-hotel-api/tests/test_repositories.py
    │       └── fastapi-hotel-api/tests/test_api.py
    ├── design-patterns/   # 37 rules, 6 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Responsibilities [HIGH]
    │   │   ├── design-single-responsibility.md
    │   │   ├── design-tell-dont-ask.md
    │   │   ├── design-split-god-class.md
    │   │   ├── design-grasp-responsibilities.md
    │   │   │ # Abstractions and coupling [HIGH]
    │   │   ├── design-low-coupling.md
    │   │   ├── design-dependency-inversion.md
    │   │   ├── design-open-closed.md
    │   │   ├── design-composition-over-inheritance.md
    │   │   ├── design-liskov-substitution.md
    │   │   ├── design-interface-segregation.md
    │   │   │ # Simplicity and restraint [HIGH]
    │   │   ├── design-dry-yagni-kiss.md
    │   │   ├── design-lightest-construct.md
    │   │   ├── design-pattern-from-smell.md
    │   │   │ # Smells and review [MEDIUM]
    │   │   ├── design-review-by-severity.md
    │   │   ├── design-start-with-the-data.md
    │   │   ├── design-name-for-intent.md
    │   │   ├── design-complete-construction.md
    │   │   │ # Common patterns [MEDIUM]
    │   │   ├── design-plugin-loading.md
    │   │   ├── design-dispatch-table.md
    │   │   ├── design-strategy.md
    │   │   ├── design-adapter.md
    │   │   ├── design-value-objects.md
    │   │   ├── design-domain-events.md
    │   │   ├── design-lazy-loading.md
    │   │   │ # Specialized patterns [LOW]
    │   │   ├── design-callback.md
    │   │   ├── design-function-wrapper.md
    │   │   ├── design-function-builder.md
    │   │   ├── design-template-method.md
    │   │   ├── design-state.md
    │   │   ├── design-builder.md
    │   │   ├── design-fluent-interface.md
    │   │   ├── design-facade.md
    │   │   ├── design-pipeline.md
    │   │   ├── design-command.md
    │   │   ├── design-singleton.md
    │   │   ├── design-abstract-factory.md
    │   │   └── design-bridge.md
    │   ├── references/
    │   │   ├── LICENSE.python-best-practices
    │   │   ├── LICENSE.python-clean-architecture
    │   │   ├── abstract-factory-progression.md
    │   │   ├── bridge-progression.md
    │   │   ├── command-progression.md
    │   │   ├── lint-guardrails.md
    │   │   ├── observer-mediator-pubsub.md
    │   │   ├── principles-and-grasp.md
    │   │   ├── quality-checklist.md
    │   │   ├── refactoring-moves.md
    │   │   ├── rule-neighbors.md
    │   │   ├── smell-catalog.md
    │   │   └── strategy-progression.md
    │   └── scripts/
    │       ├── detect_smells.py
    │       └── lcom4_clusters.py
    ├── python-architecture/   # 25 rules, 7 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Layers and imports [CRITICAL]
    │   │   ├── arch-dependency-direction.md.j2
    │   │   ├── arch-composition-root.md.j2
    │   │   ├── arch-break-import-cycles.md
    │   │   │ # Ports and boundaries [HIGH]
    │   │   ├── arch-use-case-functions.md.j2
    │   │   ├── arch-typed-records-across-layers.md.j2
    │   │   ├── arch-ports.md.j2
    │   │   │ # Domain model [HIGH]
    │   │   ├── arch-rich-domain-model.md.j2
    │   │   ├── arch-ubiquitous-language.md
    │   │   │ # Persistence [HIGH]
    │   │   ├── arch-persistence-steps.md.j2
    │   │   ├── arch-repository-port.md.j2
    │   │   ├── arch-unit-of-work.md.j2
    │   │   ├── sqlalchemy-engine-and-session-scope.md
    │   │   ├── sqlalchemy-repositories.md.j2
    │   │   ├── arch-effects-after-commit.md
    │   │   │ # Layer tests [HIGH]
    │   │   ├── arch-test-use-cases-with-fakes.md.j2
    │   │   ├── arch-contract-tests-for-fakes.md.j2
    │   │   ├── arch-tests-by-layer.md.j2
    │   │   ├── arch-make-legacy-testable.md
    │   │   │ # Project layout [MEDIUM]
    │   │   ├── arch-predictable-project-tree.md
    │   │   ├── arch-one-layout-axis.md
    │   │   ├── arch-no-junk-drawer-packages.md
    │   │   │ # CQRS and event sourcing [LOW]
    │   │   ├── arch-cqrs.md
    │   │   ├── arch-read-model-projections.md
    │   │   ├── arch-event-sourcing.md
    │   │   └── arch-event-store.md
    │   ├── references/
    │   │   ├── LICENSE.python-clean-architecture
    │   │   ├── architecture-review.md
    │   │   └── where-code-goes.md
    │   └── scripts/
    │       └── layer_map.py
    ├── python-documentation/   # 15 rules, 5 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Docs in sync [HIGH]
    │   │   ├── docs-same-change.md
    │   │   ├── docs-runnable-examples.md
    │   │   │ # Design records [HIGH]
    │   │   ├── docs-record-why.md
    │   │   ├── docs-document-layout.md
    │   │   ├── docs-architecture-overview.md
    │   │   │ # Repository files [MEDIUM]
    │   │   ├── docs-readme-essentials.md
    │   │   ├── docs-changelog.md
    │   │   ├── docs-contributing-guide.md
    │   │   ├── docs-citation-file.md
    │   │   │ # User docs [MEDIUM]
    │   │   ├── docs-page-kinds.md
    │   │   ├── sphinx-api-reference.md
    │   │   ├── mkdocs-api-reference.md
    │   │   │ # Docs build [MEDIUM]
    │   │   ├── docs-check-in-ci.md
    │   │   ├── sphinx-docs-build.md
    │   │   └── mkdocs-docs-build.md
    │   └── references/
    │       └── which-document.md
    ├── domino-apps/   # 26 rules, 6 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Launch and routing [CRITICAL]
    │   │   ├── domino-app-bind-host-port.md
    │   │   ├── domino-app-url-prefix.md
    │   │   ├── domino-app-launch-script.md
    │   │   ├── domino-app-relative-urls.md
    │   │   │ # Identity and access [CRITICAL]
    │   │   ├── domino-app-publisher-data-rights.md
    │   │   ├── domino-app-viewer-identity.md
    │   │   ├── domino-app-verify-viewer-jwt.md
    │   │   ├── domino-app-viewer-token.md
    │   │   ├── domino-app-starter-settings.md
    │   │   ├── domino-app-endpoint-auth.md
    │   │   │ # Persistence and state [CRITICAL]
    │   │   ├── domino-app-external-persistence.md
    │   │   ├── domino-app-concurrent-writes.md
    │   │   ├── domino-app-replica-state.md
    │   │   │ # Framework setup [HIGH]
    │   │   ├── domino-app-dash.md
    │   │   ├── domino-app-flask.md
    │   │   ├── domino-app-streamlit.md
    │   │   ├── domino-app-shiny.md
    │   │   ├── domino-app-static-site.md
    │   │   │ # Serving and limits [HIGH]
    │   │   ├── domino-app-production-server.md
    │   │   ├── domino-app-proxy-limits.md
    │   │   ├── domino-app-external-resources.md
    │   │   │ # Publishing and logging [MEDIUM]
    │   │   ├── domino-app-publish-from-commit.md
    │   │   ├── domino-app-deployment-record.md
    │   │   ├── domino-app-sharing-mode.md
    │   │   ├── domino-app-workspace-preview.md
    │   │   └── domino-app-logging.md
    │   └── references/
    │       └── app-troubleshooting.md
    ├── domino-jobs/   # 27 rules, 7 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Project and run environment [CRITICAL]
    │   │   ├── domino-project-types.md
    │   │   ├── domino-secrets-in-env-vars.md
    │   │   ├── domino-paths-from-env.md
    │   │   ├── domino-api-proxy-auth.md
    │   │   ├── domino-env-var-names.md
    │   │   ├── domino-pinned-environments.md
    │   │   ├── domino-environment-revisions.md
    │   │   │ # Entry points and exit codes [CRITICAL]
    │   │   ├── domino-job-exit-codes.md
    │   │   ├── domino-job-entry-point.md
    │   │   ├── domino-launcher-arguments.md
    │   │   ├── domino-launcher-uploads.md
    │   │   │ # Datasets [HIGH]
    │   │   ├── domino-datasets-for-large-data.md
    │   │   ├── domino-run-scoped-writes.md
    │   │   ├── domino-dataset-snapshots.md
    │   │   ├── domino-materialize-external-data.md
    │   │   │ # Scheduling and launching [HIGH]
    │   │   ├── domino-job-schedules.md
    │   │   ├── domino-idempotent-jobs.md
    │   │   ├── domino-spot-checkpoints.md
    │   │   ├── domino-launch-jobs-from-code.md
    │   │   │ # Flow tasks [HIGH]
    │   │   ├── domino-flow-task-io.md
    │   │   ├── domino-flow-task-purity.md
    │   │   │ # Results and metrics [MEDIUM]
    │   │   ├── domino-job-results.md
    │   │   ├── domino-job-logging.md
    │   │   ├── domino-job-stats-file.md
    │   │   ├── domino-job-email-report.md
    │   │   │ # Reproducibility [MEDIUM]
    │   │   ├── domino-run-manifest.md
    │   │   └── domino-mlflow-tracking.md
    │   └── references/
    │       └── where-outputs-go.md
    ├── domino-agents/   # 23 rules, 7 sections
    │   ├── SKILL.md
    │   ├── rules/
    │   │   │ # Secrets and tokens [CRITICAL]
    │   │   ├── domino-agent-llm-keys.md
    │   │   ├── domino-agent-access-token.md
    │   │   ├── domino-agent-endpoint-auth.md
    │   │   ├── domino-agent-redact-traces.md
    │   │   │ # Agent service [HIGH]
    │   │   ├── domino-agent-app-factory.md
    │   │   ├── domino-agent-chat-endpoint.md
    │   │   ├── domino-agent-run-limits.md
    │   │   ├── domino-agent-conversation-state.md
    │   │   ├── domino-agent-logging.md
    │   │   │ # Configuration [HIGH]
    │   │   ├── domino-agent-settings.md
    │   │   ├── domino-agent-config-file.md
    │   │   │ # Tracing [HIGH]
    │   │   ├── domino-agent-trace-entrypoint.md
    │   │   ├── domino-agent-manual-spans.md
    │   │   ├── domino-agent-sdk-names.md
    │   │   │ # Evaluation [HIGH]
    │   │   ├── domino-agent-dev-eval-job.md
    │   │   ├── domino-agent-evaluators.md
    │   │   ├── domino-agent-eval-out-of-band.md
    │   │   ├── domino-agent-prod-eval-watermark.md
    │   │   │ # A2A protocol [MEDIUM]
    │   │   ├── a2a-mount-lifespan.md
    │   │   ├── a2a-agent-card.md
    │   │   ├── a2a-client-deadlines.md
    │   │   │ # Testing [MEDIUM]
    │   │   ├── domino-agent-fake-llm-tests.md
    │   │   └── domino-agent-fake-domino-tests.md
    │   ├── references/
    │   │   ├── LICENSE.simple-agent-api
    │   │   ├── agent-lifecycle.md
    │   │   └── credentials-by-call.md
    │   └── examples/
    │       ├── simple-agent-api/README.md
    │       ├── simple-agent-api/pyproject.toml
    │       ├── simple-agent-api/app.sh
    │       ├── simple-agent-api/agent_config.yaml
    │       ├── simple-agent-api/sample_questions.csv
    │       ├── simple-agent-api/app/settings.py
    │       ├── simple-agent-api/app/logs.py
    │       ├── simple-agent-api/app/domino_token.py
    │       ├── simple-agent-api/app/llm.py
    │       ├── simple-agent-api/app/agent.py
    │       ├── simple-agent-api/app/tracing.py
    │       ├── simple-agent-api/app/chat.py
    │       ├── simple-agent-api/app/a2a.py
    │       ├── simple-agent-api/app/main.py
    │       ├── simple-agent-api/app/asgi.py
    │       ├── simple-agent-api/evals/evaluators.py
    │       ├── simple-agent-api/evals/trace_store.py
    │       ├── simple-agent-api/evals/dev_eval.py
    │       ├── simple-agent-api/evals/prod_eval.py
    │       ├── simple-agent-api/tests/conftest.py
    │       ├── simple-agent-api/tests/fakes.py
    │       ├── simple-agent-api/tests/test_api.py
    │       ├── simple-agent-api/tests/test_agent.py
    │       ├── simple-agent-api/tests/test_domino_token.py
    │       └── simple-agent-api/tests/test_evals.py
    └── playbook-creator/   # 19 rules, 7 sections
        ├── SKILL.md
        ├── rules/
        │   │ # Layers [CRITICAL]
        │   ├── playbook-ask-for-missing-inputs.md.j2
        │   ├── playbook-layer-placement.md
        │   ├── playbook-override-by-id.md
        │   │ # Rules [CRITICAL]
        │   ├── playbook-rule-frontmatter.md
        │   ├── playbook-rule-ids.md
        │   ├── playbook-rule-gates.md
        │   ├── playbook-rule-templates.md
        │   ├── playbook-rule-body.md
        │   │ # Validation [CRITICAL]
        │   ├── playbook-validate-and-sync.md
        │   ├── playbook-engine-catalog-gate.md
        │   │ # Skills [HIGH]
        │   ├── playbook-skill-sections.md
        │   ├── playbook-skill-md.md
        │   ├── playbook-skill-files.md
        │   │ # Hooks [HIGH]
        │   ├── playbook-hook-definition.md
        │   ├── playbook-hook-guardrails.md
        │   │ # Prompts and eval samples [HIGH]
        │   ├── playbook-prompt-frontmatter.md
        │   ├── playbook-eval-samples.md
        │   │ # Plugins and overlays [MEDIUM]
        │   ├── playbook-plugin-layout.md
        │   └── playbook-third-party-content.md
        └── references/
            ├── eval-sample-template.md
            ├── hook-template.md
            ├── plugin-template.md
            ├── prompt-template.md
            ├── rule-template.md
            └── skill-template.md
```
