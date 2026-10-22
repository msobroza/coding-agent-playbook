---
id: domino-app-relative-urls
name: Relative URLs
description: "Build every link, redirect, fetch and asset path relative to the App's prefix; never start one at '/' or name a host."
version: 1
scope: scoped
globs:
  - "**/app.py"
  - "**/run.py"
  - "**/views.py"
  - "**/callbacks.py"
  - "**/pages/*.py"
  - "**/templates/**/*.html"
  - "**/static/**/*.js"
  - "**/assets/**/*.js"
applies_if:
  domino_project: true
section: launch
priority: 23
tags: [python, domino, apps]
---

# Relative URLs

## Description

Viewers reach the App through a path prefix that changes with the App's custom URL path and with the secure identity flag. A link that starts at `/`, or names a host, leaves that prefix: the proxy answers 404, stylesheets and scripts fail to load, and the page looks blank or broken. Build URLs with the framework helpers that know the prefix, or keep them relative to the current page.

## Bad Example

```html
<link rel="stylesheet" href="/static/app.css">
<script>
  fetch("/api/data").then((response) => response.json());
</script>
```

```python
from flask import redirect
from werkzeug.wrappers import Response


def logout() -> Response:
    return redirect("/login")
```

## Good Example

```html
<link rel="stylesheet" href="{{ url_for('static', filename='app.css') }}">
<script>
  fetch("api/data").then((response) => response.json());
</script>
```

```python
from flask import redirect, url_for
from werkzeug.wrappers import Response


def logout() -> Response:
    # url_for knows the prefix once SCRIPT_NAME is set (domino-app-flask).
    return redirect(url_for("login"))
```

In Dash, link assets with `app.get_asset_url("logo.png")` and pages with `app.get_relative_path("/reports")`.

## Notes

- Never write a host name into code; viewers get links from the App's copy-link button.
- A redirect the framework cannot build is joined onto the configured prefix (`domino-app-url-prefix`), never onto `/`.
- Agent APIs on Domino apply the same rule to their docs and static routes (domino-agents skill).
