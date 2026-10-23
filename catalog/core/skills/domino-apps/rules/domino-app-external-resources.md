---
id: domino-app-external-resources
name: External resources
description: "Vendor fonts, scripts and styles into the App's static folder and call outside APIs from the server, so a content security policy cannot break the page."
version: 1
scope: scoped
globs:
  - "**/templates/**/*.html"
  - "**/assets/**"
  - "**/static/**"
  - "**/app.py"
applies_if:
  domino_project: true
section: serving
priority: 47
tags: [python, domino, apps, security]
---

# External resources

## Description

In Domino 6.2 the content security policy for Apps is off by default, but an admin can turn it on at any time without a restart of the platform. Where it is on, or where iframe restrictions apply, the browser refuses every font, script, style, API call or embedded page served from another host unless an admin has allowlisted it. Nothing fails on the server: the page simply renders without its chart library or its fonts, and the only trace is in the viewer's browser console.

An App that loads nothing from other hosts keeps working whatever the deployment decides.

## Bad Example

```html
<head>
  <link rel="stylesheet" href="https://fonts.example.com/css?family=Inter">
  <script src="https://cdn.example.com/charts/4.4.0/charts.min.js"></script>
</head>
<script>
  fetch("https://api.example.com/rates").then((r) => r.json()).then(draw);
</script>
```

## Good Example

```html
<head>
  <link rel="stylesheet" href="static/fonts/inter.css">
  <script src="static/vendor/charts-4.4.0.min.js"></script>
</head>
<script>
  fetch("api/rates").then((r) => r.json()).then(draw);
</script>
```

```python
import httpx
from flask import Flask, jsonify
from flask.typing import ResponseReturnValue


def register_rates(app: Flask, client: httpx.Client) -> None:
    @app.get("/api/rates")
    def rates() -> ResponseReturnValue:
        # The outside API is called from the server, with the client's timeout.
        response = client.get("/rates")
        response.raise_for_status()
        return jsonify(response.json())
```

The font and the chart library are copied into the App's static folder (Dash serves `assets/`, Flask serves `static/`) and referenced by relative paths; the browser talks only to the App. The shared `httpx.Client` is built once in the composition root with a base URL from settings and a timeout.

## Notes

- Diagnose a blank or unstyled page in the browser console: "refused to load" messages name the blocked host. Send them to the admin, and restart the App after the allowlist changes.
- Embedding the App in an outside page is restricted by default; do not design around being framed.
- Turn framework telemetry off (Streamlit's usage statistics), which also avoids blocked requests (`domino-app-streamlit`).
- Links and asset paths stay relative (`domino-app-relative-urls`); outside calls follow `python-retries-and-timeouts` (python-coding skill).
