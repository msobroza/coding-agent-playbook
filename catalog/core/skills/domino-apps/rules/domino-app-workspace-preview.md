---
id: domino-app-workspace-preview
name: Workspace preview
description: "Preview an App from a workspace with a separate dev script on a free port; never reuse the preview URL as the published App's prefix."
scope: scoped
globs:
  - "**/app.sh"
  - "**/start.sh"
  - "**/dev.sh"
applies_if:
  domino_project: true
section: publishing
priority: 63
tags: [domino, apps, shell]
---

# Workspace preview

## Description

A workspace exposes one port of its own, and ports 80 and 9000 are reserved. To try an App before publishing, start its server on another port and open it through the workspace's server proxy, at a path built from the project owner, the project name and the run id. A published App works differently: it serves port 8888 under the prefix in `DOMINO_RUN_HOST_PATH`.

Mixing the two is how hand-built prefixes reach production: a helper that assembles the preview path works in the workspace and breaks the published App at its next restart.

## Bad Example

```python
import os


def base_path() -> str:
    # Used for the workspace preview AND as the published App's prefix.
    owner = os.environ["DOMINO_PROJECT_OWNER"]
    project = os.environ["DOMINO_PROJECT_NAME"]
    run_id = os.environ["DOMINO_RUN_ID"]
    return f"/{owner}/{project}/notebookSession/{run_id}/proxy/8888/"
```

## Good Example

```bash
#!/usr/bin/env bash
# dev.sh: workspace preview only; never selected as the launch file.
set -euo pipefail

PORT="${DEV_PORT:-8050}"  # not 80, 9000 or the workspace's own port
PREVIEW="/${DOMINO_PROJECT_OWNER}/${DOMINO_PROJECT_NAME}/notebookSession/${DOMINO_RUN_ID}/proxy/${PORT}/"
echo "Preview at ${PREVIEW}"

export APP_URL_PREFIX="${PREVIEW}"
exec gunicorn --bind 0.0.0.0:"${PORT}" --workers 1 myapp.wsgi:app
```

The App reads one setting for its prefix; `dev.sh` fills it with the preview path, while the published `app.sh` fills it from `DOMINO_RUN_HOST_PATH` and serves 8888 (`domino-app-bind-host-port`, `domino-app-url-prefix`). No Python code builds either path.

## Notes

- A framework that needs its browser prefix (Dash) gets the preview path the same way during preview (inferred, check it in the workspace).
- In a file-system project, stop the workspace so its files sync before publishing (`domino-app-publish-from-commit`).
- Streamlit previews on its own default port and publishes on 8888 (`domino-app-streamlit`).
- A preview that works while the published App shows a blank page usually means a prefix built by hand somewhere in the code.
