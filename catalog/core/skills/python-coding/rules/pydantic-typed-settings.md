---
id: pydantic-typed-settings
name: Typed settings
description: "Load all configuration into one BaseSettings class at startup: required per-environment values, SecretStr secrets, built once and passed in."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  has_dependency: ["pydantic-settings"]
section: pydantic
priority: 59
tags: [python, pydantic, configuration]
---

# Load configuration into one typed settings object

## Description

`os.getenv("X", "default")` scattered across modules postpones failures to runtime, turns a typo into a silent default and invites insecure fallbacks. Declare all configuration in one `pydantic-settings` class instead.

- Values that change per environment (URLs, credentials, feature flags, deployment-tuned timeouts) live only in this object and have no default.
- Secrets are `SecretStr`; every value is validated.
- Construct it once, in the entrypoint or composition root, so a missing or invalid value fails at startup, and pass it to the code that needs it. Business code never imports a module-level settings instance and never reads the environment at import time.

## Bad Example

```python
# billing.py
SIGNING_KEY = os.getenv("SIGNING_KEY", "dev-key")  # production signs with "dev-key"
TIMEOUT = int(os.getenv("TIMEOUT_SECONDS", "15"))  # "15s" crashes at import


# config.py
class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")  # the plain model config, not the settings one

    database_url: str = DEV_DATABASE_URL  # an unset variable silently selects the dev database
    api_key: str = ""  # an empty secret passes
```

## Good Example

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    database_url: SecretStr  # required: no default
    signing_key: SecretStr = Field(min_length=32)
    payments_base_url: str
    payments_api_key: SecretStr
    request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    allowed_origins: list[str] = Field(default_factory=list)  # JSON in the environment


def main() -> None:
    settings = Settings()  # the one place that reads the environment
    run(build_service(settings))  # a ValidationError here lists every missing field
```

## Notes

- `SecretStr` prints as `'**********'` in `repr`, logs and tracebacks; call `get_secret_value()` only where the value is used, such as building the database engine.
- Tests build `Settings(...)` with test values and pass it in; no environment patching is needed.
- `.env` is for local development only: keep it in `.gitignore` and commit a `.env.example` without values. In production the platform's secret store injects environment variables.
- Group related settings in nested models with `env_nested_delimiter="__"` (`APP_DB__POOL_SIZE=10`).
- Hand a callee the few values it uses rather than the whole object (`python-dependency-injection`); a cached `get_settings()` accessor is a global in disguise (`python-no-global-singletons`).
- The Pydantic mypy plugin, which lets `Settings()` without arguments type-check, is the python-tooling skill's mypy-type-checking rule. Wiring settings into a FastAPI app is the web-application skill's fastapi-app-wiring rule.
