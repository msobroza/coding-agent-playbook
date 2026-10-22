---
id: domino-app-flask
name: Flask on Domino
description: "Mount a Flask App at DOMINO_RUN_HOST_PATH with a small WSGI middleware so url_for and redirects keep the prefix and the proxy's https scheme."
version: 1
scope: scoped
globs:
  - "**/app.py"
  - "**/run.py"
  - "**/wsgi.py"
  - "**/views.py"
  - "**/templates/**/*.html"
applies_if:
  domino_project: true
  has_framework: ["flask"]
section: frameworks
priority: 41
tags: [python, domino, apps, flask]
---

# Flask on Domino

Flask builds every URL from its mount point (`SCRIPT_NAME`) and the request's scheme. Behind the Domino proxy it sees neither: without help, `url_for` drops the App's prefix and a redirect points at plain http, so links return 404 and the browser warns or refuses.

## Bad Example

```python
from flask import Flask, redirect, url_for
from werkzeug.wrappers import Response

app = Flask(__name__)


@app.get("/")
def index() -> Response:
    return redirect(url_for("report"))  # "/report": outside the App, and over http
```

## Good Example

```python
from collections.abc import Callable, Iterable
from typing import Any

from flask import Flask

from sales_app.config import AppConfig  # url_prefix as domino-app-url-prefix loads it

WSGIApp = Callable[[dict[str, Any], Callable[..., Any]], Iterable[bytes]]


class PrefixMiddleware:
    """Tells Flask where the proxy mounts it and which scheme viewers use."""

    def __init__(self, app: WSGIApp, *, prefix: str) -> None:
        self._app = app
        self._prefix = prefix.rstrip("/")

    def __call__(
        self, environ: dict[str, Any], start_response: Callable[..., Any]
    ) -> Iterable[bytes]:
        path = environ.get("PATH_INFO", "")
        if self._prefix and path.startswith(self._prefix):
            environ["PATH_INFO"] = path[len(self._prefix) :] or "/"
        environ["SCRIPT_NAME"] = self._prefix
        environ["wsgi.url_scheme"] = environ.get("HTTP_X_SCHEME", "https")
        return self._app(environ, start_response)


def create_app(config: AppConfig) -> Flask:
    app = Flask(__name__)
    # Flask types wsgi_app as a method; WSGI middleware replaces it by design.
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=config.url_prefix)  # type: ignore[method-assign]
    return app
```

```bash
exec gunicorn --bind 0.0.0.0:8888 --workers "${APP_WORKERS:-2}" "wsgi:app"
```

## Notes

- The prefix is `DOMINO_RUN_HOST_PATH` as `domino-app-url-prefix` normalizes it (one leading and one trailing slash, `/` locally; its form changes with the secure flag and a custom URL path), never a request header a client could send. The middleware drops the trailing slash, since `SCRIPT_NAME` takes none.
- Keep `static/` and `templates/` beside the app package; Flask finds them by name. Build every link with `url_for` (`domino-app-relative-urls`).
- werkzeug's `ProxyFix` reads the `X-Forwarded-*` family but not the `X-Scheme` header Domino documents, and the prefix comes from the variable anyway, so the small middleware stays (the engine's inference; check the links on a published App).
- Serve with gunicorn and debug off (`domino-app-production-server`); the development server is single-threaded.
- Behind the proxy the App is same-origin and needs no CORS; if a route adds it, follow `web-cors-origins` (web-application).
