---
id: web-cors-origins
name: List allowed CORS origins explicitly
description: "Read the exact list of trusted CORS origins from settings, default to none, never allow every origin together with credentials, and allow only the methods and headers the frontend uses."
scope: scoped
globs:
  - "**/main.py"
  - "**/app.py"
  - "**/asgi.py"
  - "**/deps.py"
  - "**/dependencies.py"
  - "**/settings.py"
  - "**/config.py"
applies_if:
  any_framework: ["fastapi", "flask", "django", "starlette"]
section: security
priority: 24
tags: [python, web, security, cors]
---

# List allowed CORS origins explicitly

## Description

CORS tells browsers which other sites may read your API's responses. `allow_origins=["*"]` with `allow_credentials=True` does not mean "public API": Starlette echoes the caller's `Origin` with `Access-Control-Allow-Credentials: true`, so script on any website can send the user's cookies and read the result. Load the exact list of trusted origins from settings, default to none, and allow only the methods and headers the frontend uses.

## Bad Example

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,  # with "*", Starlette reflects any Origin
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Good Example

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")

    # APP_CORS_ORIGINS='["https://app.example.com"]'
    cors_origins: list[str] = Field(default_factory=list)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # empty means no cross-origin access
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    return app
```

## Notes

- Origins match exactly: scheme, host and port all count, so the https and http forms of one host, and its `www` subdomain, are three different origins. Do not add a trailing slash.
- `allow_origin_regex` is matched with `fullmatch`, so escape the dots: an unescaped `.*example.com` also matches `evilexample.com`; write the host part as `[a-z0-9-]+\.example\.com`.
- A public, cookie-less API may use `allow_origins=["*"]` with `allow_credentials=False`.
- CORS is neither authentication nor CSRF protection. It only controls what browsers expose to scripts; curl and servers ignore it. Cookie-based auth still needs `SameSite` cookies or CSRF tokens.
- When the frontend is served from the same origin (for example behind one reverse proxy), you need no `CORSMiddleware` at all.
- Django and Flask CORS extensions follow the same rule: an explicit origin list read from settings, and never every origin together with credentials.
