---
id: domino-app-publisher-data-rights
name: Publisher data rights
description: "Treat mounted Datasets, volumes and data sources as the publisher's access; read per-viewer data through a port built from the viewer's identity."
scope: scoped
globs:
  - "**/app.py"
  - "**/views.py"
  - "**/callbacks.py"
  - "**/auth.py"
  - "**/identity.py"
  - "**/data.py"
  - "**/queries.py"
applies_if:
  domino_project: true
section: access
priority: 24
tags: [python, domino, apps, security]
---

# Publisher data rights

## Description

Whatever identity a request carries, the data an App reaches through the file system or a configured connection acts with the rights of the person who published or started it: mounted Datasets and NetApp Volumes, and data-source connections that use stored credentials. Every viewer of the App can therefore read, and where mounting is read-write change, everything that person can. The Domino 6.2 pages disagree about the default identity of an App, so assume the publisher's rights apply and design for that.

When viewers must see only their own data, the App reads it through the Data API SDK (`dominodatalab-data`, imported as `domino_data`) with the viewer's username or token, never through the mount.

## Bad Example

```python
from pathlib import Path

DATA_ROOT = Path("/mnt/data/sales")


def files_for(customer: str) -> list[str]:
    # Filtered by a name the viewer typed: any viewer can list any customer's files.
    return sorted(path.name for path in (DATA_ROOT / customer).iterdir())
```

## Good Example

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Viewer:
    username: str


class ViewerScopedReader(Protocol):
    """Reads only what the given viewer may read."""

    def list_reports(self, viewer: Viewer) -> list[str]: ...


class FakeViewerScopedReader:
    """Test double: each viewer sees only the reports seeded for them."""

    def __init__(self, reports: dict[str, list[str]]) -> None:
        self._reports = reports

    def list_reports(self, viewer: Viewer) -> list[str]:
        return list(self._reports.get(viewer.username, []))


def reports_page(reader: ViewerScopedReader, viewer: Viewer) -> list[str]:
    return reader.list_reports(viewer)
```

The production adapter implements `ViewerScopedReader` with a Data API client built per request from that viewer's token (`domino-app-viewer-token`), so the token never rides on `Viewer`; the page depends only on the Protocol.

## Notes

- Leave dataset mounting off in the publish dialog unless the App needs it; mounting is chosen per App.
- Each record a viewer opens is still authorized in the App (`web-object-authorization`, web-application skill, where a web framework is declared).
- "Allow App to act for viewers" is admin-only, needs a restart and hands the App each viewer's full access (`domino-app-viewer-token`).
- Dataset paths come from the environment, never literals (`domino-paths-from-env`, domino-jobs skill).
- The viewer comes from a verified token (`domino-app-verify-viewer-jwt`), not a header alone.
