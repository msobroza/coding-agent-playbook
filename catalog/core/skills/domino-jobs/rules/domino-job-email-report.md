---
id: domino-job-email-report
name: Job email report
description: "Write email.html with a title, inline styles and escaped values at the output root, and list it in .dominoresults when that file exists."
version: 1
scope: scoped
globs:
  - "email.html"
  - "**/*.py"
applies_if:
  domino_project: true
section: results-and-metrics
priority: 63
tags: [python, domino, jobs, results]
---

# Write a custom success email as email.html

## Description

On success Domino emails the last lines of stdout and up to ten result files. A run that writes `email.html` replaces that body, and the file's `<title>` becomes the subject behind a `[Domino]` prefix. The file goes at the project root in DFS projects and at the artifacts root in Git-based projects, and when `.dominoresults` exists it must list `email.html`, or the default email is sent instead.

Email clients drop `<style>` blocks and CSS positioning, so the HTML uses inline styles and tables, and images are referenced by paths from the project root. Values that come from data or inputs are escaped.

## Bad Example

```python
html = (
    "<html><head><style>.grid { display: flex }</style></head><body>"
    f'<div class="grid">{customer_name}: {score}</div>'
    '<img src="https://cdn.example.com/logo.png"></body></html>'
)
Path("/mnt/code/email.html").write_text(html, encoding="utf-8")  # the Git checkout, not results
```

The style block and flexbox are dropped, the external image is blocked, the values are not escaped, and the file lands where Domino does not look for it.

## Good Example

```python
from collections.abc import Sequence
from html import escape
from pathlib import Path

CELL = 'style="padding:4px 8px;border:1px solid #ccc;font-family:sans-serif"'


def render_email(title: str, rows: Sequence[tuple[str, str]]) -> str:
    body = "".join(
        f"<tr><td {CELL}>{escape(name)}</td><td {CELL}>{escape(value)}</td></tr>"
        for name, value in rows
    )
    return (
        f"<html><head><title>{escape(title)}</title></head><body>"
        f'<table style="border-collapse:collapse">{body}</table></body></html>'
    )


def write_email(output_root: Path, title: str, rows: Sequence[tuple[str, str]]) -> None:
    (output_root / "email.html").write_text(render_email(title, rows), encoding="utf-8")
```

`output_root` is the project root in DFS projects and the artifacts root in Git-based ones (domino-project-types).

## Notes

- One 6.2 tip spells the file `emails.html`; the name is `email.html`.
- The custom body applies to the success email; failure emails are still sent by default.
- Launcher runs mail their notification list; Launcher inputs are domino-launcher-arguments and domino-launcher-uploads.
- Emails leave Domino, so include no secrets and only the data readers need. Recipients' preferences live in the project settings.
