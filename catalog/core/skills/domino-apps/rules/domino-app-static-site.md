---
id: domino-app-static-site
name: Static site on Domino
description: "Serve a static Domino App from a dedicated folder of published files on 0.0.0.0:8888, never from the project's working directory."
version: 1
scope: scoped
globs:
  - "**/app.py"
  - "**/site/**/*.html"
  - "**/index.html"
applies_if:
  domino_project: true
section: frameworks
priority: 44
tags: [python, domino, apps]
---

# Static site on Domino

The standard library's HTTP server can publish a few static pages as an App, with the Python file selected as the launch file. Its file handler shares everything under its directory, and by default that directory is the working directory: the whole project, code, data and configuration included. That exposure is the engine's inference from how the handler works; the docs' own example serves the working directory as is.

## Bad Example

```python
from http.server import HTTPServer, SimpleHTTPRequestHandler

HTTPServer(("0.0.0.0", 8888), SimpleHTTPRequestHandler).serve_forever()  # serves the project
```

## Good Example

```python
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent / "site"  # only the published files


def main() -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(SITE_DIR))
    with ThreadingHTTPServer(("0.0.0.0", 8888), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
```

## Notes

- Fine for a few viewers of static content. Anything that reads the viewer, stores data or computes per request belongs in a framework (`domino-app-flask`, `domino-app-dash`).
- Links inside the pages stay relative, because the App lives under a prefix (`domino-app-relative-urls`).
- Keep the site folder free of secrets and data exports; whatever sits in it is public to every viewer of the App.
