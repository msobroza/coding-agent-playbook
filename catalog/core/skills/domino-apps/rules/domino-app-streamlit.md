---
id: domino-app-streamlit
name: Streamlit on Domino
description: "Start a Streamlit App through streamlit run with an explicit 0.0.0.0:8888, headless and without telemetry, keeping CORS and XSRF protection on."
version: 1
scope: scoped
globs:
  - "**/app.sh"
  - "**/.streamlit/config.toml"
  - "**/streamlit_app.py"
  - "**/app.py"
  - "**/pages/*.py"
applies_if:
  domino_project: true
  has_dependency: ["streamlit"]
section: frameworks
priority: 42
tags: [python, domino, apps, streamlit]
---

# Streamlit on Domino

A Streamlit script starts a server only through Streamlit's own CLI, and that server listens on port 8501 unless told otherwise. A published App must serve `0.0.0.0:8888`, so the launch script sets both values explicitly.

## Bad Example

```bash
python app.py            # runs the script once; no server starts
streamlit run app.py     # port 8501: the App never becomes reachable
```

## Good Example

```bash
#!/usr/bin/env bash
set -euo pipefail
exec streamlit run app.py \
  --server.port=8888 \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false
```

Or the same keys in a committed `.streamlit/config.toml`, with a plain `exec streamlit run app.py` in the launch script:

```toml
[server]
port = 8888
address = "0.0.0.0"
headless = true

[browser]
gatherUsageStats = false
```

## Notes

- Keep CORS and XSRF protection on. Turning either off needs a recorded reason and proof that the proxy requires it; the docs document none.
- Streamlit resolves its assets and websocket relative to the page, and the 6.2 docs do not say whether the proxy forwards the prefix. Set `--server.baseUrlPath` only from `DOMINO_RUN_HOST_PATH`, and only when a published test App shows it is needed (`domino-app-url-prefix`).
- Usage statistics off also avoids requests a content security policy would block (`domino-app-external-resources`).
- `st.session_state` lives per connection and is lost on a reconnect to another pod (`domino-app-replica-state`).
- Read viewer headers through `st.context.headers` (`domino-app-viewer-identity`).
- Secrets come from environment variables, never a committed `.streamlit/secrets.toml` (domino-secrets-in-env-vars, domino-jobs).
- Keep `server.maxUploadSize` at or below the proxy's body limit (`domino-app-proxy-limits`).
