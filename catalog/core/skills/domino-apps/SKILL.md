---
id: domino-apps
name: domino-apps
description: "Guides Domino 6.2 Apps served behind the platform proxy."
playbook:
  use_when: "writing or changing a Domino App or its launch script, agent APIs included"
  files: "Domino App code and its launch scripts (app.sh, start.sh)"
  sections:
    - id: launch
      title: "Launch and routing"
      impact: CRITICAL
      summary: "Start the server where the proxy can reach it and keep every URL under the App's prefix."
      open_when: "An App's or agent API's launch script (app.sh) is written, or code sets its host, port or URL prefix, or builds a link, redirect or asset URL."
    - id: access
      title: "Identity and access"
      impact: CRITICAL
      summary: "Know whose rights the App runs with, identify viewers safely and keep their tokens private."
      open_when: "App code reads the viewer's domino-username or token, a mounted Dataset, a data source or a user-variable key, or calls a Domino model API."
    - id: state
      title: "Persistence and state"
      impact: CRITICAL
      summary: "Store data outside the container and keep it correct across restarts, viewers and replicas."
      open_when: "App code writes a file, saves what a viewer entered, or keeps per-viewer data in memory between requests."
    - id: frameworks
      title: "Framework setup"
      impact: HIGH
      summary: "What Dash, Flask, Streamlit, Shiny for Python and static pages each need to run behind the proxy."
      open_when: "A Dash(...), Flask(...), Streamlit config, Shiny App or http.server object is created or its options change."
    - id: serving
      title: "Serving and limits"
      impact: HIGH
      summary: "Serve many viewers within the proxy's timeout, body-size and content-policy limits."
      open_when: "An App picks gunicorn or a worker count, a handler runs long or takes uploads, or a page loads assets from another host."
    - id: publishing
      title: "Publishing and logging"
      impact: MEDIUM
      summary: "Publish pushed code on a pinned environment, share deliberately, preview and log the right way."
      open_when: "An App is published, republished or previewed in a workspace, its viewers are chosen, or App code adds logging."
  references:
    - path: references/app-troubleshooting.md
      open_when: "An App never reaches Running, shows a blank page or a 404/502/504/413, loses data or sessions, or changed after a restart."
      applies_if:
        domino_project: true
---

# Domino Apps

A Domino App is project code served from its own container behind an authenticating proxy that every viewer's request passes through. This skill targets Domino 6.2; where a newer release behaves differently, the rule says so. Most of an App's settings (launch file, environment, hardware tier, branch, sharing) live in the Domino UI, not in the repository, so the code and its notes must carry what the UI does not show.

## Quick reference

The App contract:

- The server listens on `0.0.0.0`, port `8888`; any other port or a loopback bind leaves the App starting forever.
- The URL prefix comes from `DOMINO_RUN_HOST_PATH`, read once at startup; links, redirects and assets stay under it.
- The viewer is named by the `domino-username` header (`Anonymous` when nobody is signed in); only a verified `Authorization` token proves who it is.
- Mounted Datasets and data sources act with the publisher's rights, for every viewer.
- User-level variables come from whoever last started the App, not from the viewer.
- Files written at runtime vanish at the next stop, restart or scale event.
- Requests finish well under the proxy's 300 s default timeout, and uploads stay under 25 MiB.

One launch line per framework, as the last command of `app.sh`:

```bash
exec gunicorn --bind 0.0.0.0:8888 --workers 4 app:server    # Dash
exec gunicorn --bind 0.0.0.0:8888 --workers 4 app:app       # Flask
exec streamlit run app.py --server.port=8888 --server.address=0.0.0.0 --server.headless=true
exec shiny run --host 0.0.0.0 --port 8888 app:app           # Shiny for Python
```

## See also

- domino-jobs: shared Domino basics (variable names, secrets, project types, paths, environments).
- domino-agents: agent services hosted as Apps.
- web-application, python-coding, python-architecture and python-testing: the code behind the App.
