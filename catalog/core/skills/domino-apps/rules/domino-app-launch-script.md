---
id: domino-app-launch-script
name: Launch script
description: "Keep the launch script small and executable, and end it by exec-ing one foreground server command."
scope: scoped
globs:
  - "**/app.sh"
  - "**/start.sh"
applies_if:
  domino_project: true
section: launch
priority: 22
tags: [domino, apps, shell]
---

# Launch script

## Description

The launch file is what the publish dialog selects, and the process it starts is what Domino watches. When that process exits, the App is down; whether Domino starts it again depends on platform settings, so never rely on a restart. The server therefore runs in the foreground as the script's last command, replacing the shell with `exec` so signals reach it directly.

A launch script that installs packages, starts the server in the background or does real work slows every start and hides failures.

## Bad Example

```bash
#!/usr/bin/env bash
pip install dash pandas
python app.py &
echo "started"
```

## Good Example

```bash
#!/usr/bin/env bash
set -euo pipefail

# Non-secret settings only; secrets come from Domino environment variables.
export PYTHONUNBUFFERED=1
export APP_WORKERS="${APP_WORKERS:-4}"

exec gunicorn --bind 0.0.0.0:8888 --workers "${APP_WORKERS}" myapp.wsgi:app
```

Commit the executable bit with the file:

```bash
git update-index --chmod=+x app.sh
```

## Notes

- The file name is free (`app.sh`, `start.sh`, a Python file); it is picked at publish time. Keep it at the project root.
- Keep the entry module to layout, routing and callbacks; business logic and data loading live in importable modules (`arch-use-case-functions`, python-architecture skill).
- Packages belong in the compute environment, not installed at every start (`domino-pinned-environments`, domino-jobs skill).
- Never echo secrets or tokens from the script (`domino-app-viewer-token`; `domino-secrets-in-env-vars`, domino-jobs skill).
- Host and port follow `domino-app-bind-host-port`; the production server follows `domino-app-production-server`.
- A start that never completes: see app-troubleshooting.md.
