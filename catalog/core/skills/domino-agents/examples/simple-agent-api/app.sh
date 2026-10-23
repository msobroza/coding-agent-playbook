#!/usr/bin/env bash
# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
# The App's (and Deploy Agent's) entrypoint: one foreground uvicorn process on the
# address and port Domino routes to. One worker, because the A2A tasks live in
# process memory; nothing is installed at start and the log level comes from settings.
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
log_level="$(printf '%s' "${SIMPLE_AGENT_LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')"

exec uvicorn app.asgi:app --host 0.0.0.0 --port 8888 --workers 1 --log-level "$log_level"
