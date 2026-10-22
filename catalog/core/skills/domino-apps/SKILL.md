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
---

# Domino Apps

A Domino App is project code served from its own container, behind a proxy that authenticates every viewer and forwards each request under the App's own URL prefix. This skill targets Domino 6.2; where older or newer releases behave differently, the rule says so. Most of an App's settings (launch file, environment revision, hardware tier, branch, sharing mode) live in the Domino UI, not in the repo, so the repo has to record them itself.

## Quick Reference

The App contract:

- Bind the server to `0.0.0.0` on port `8888`; any other port or a loopback host leaves the App stuck starting.
- Read the URL prefix from `DOMINO_RUN_HOST_PATH` at startup; never assemble it from the owner, project and run id.
- Identify the viewer from the `domino-username` header, or, for decisions that guard data, from the verified `Authorization` JWT.
- Mounted Datasets and data sources act with the publisher's or starter's rights, not the viewer's.
- User-level environment variables come from whoever last started the App.
- Files written at runtime vanish at the next stop, restart or scale event; keep durable data in a Dataset, a database or an object store.
- Keep each request well under the proxy's 300 s default timeout and each upload under 25 MiB; longer work goes to a Job.

One launch line per framework, the last command of `app.sh`:

```bash
exec gunicorn --bind 0.0.0.0:8888 --workers 2 app:server       # Dash
exec gunicorn --bind 0.0.0.0:8888 --workers 2 app:app          # Flask
exec streamlit run app.py --server.port=8888 --server.address=0.0.0.0
exec shiny run --host 0.0.0.0 --port 8888 app:app              # Shiny for Python
```

## See Also

- domino-jobs: variable names, secrets, project types, paths and pinned environments shared by every Domino run.
- domino-agents: agent APIs hosted as Domino Apps.
- web-application, python-coding, python-architecture and python-testing: the general web, code, layering and test guidance an App's code also follows.
