---
id: domino-materialize-external-data
name: Domino materialized external data
description: "Write the exact extract a job reads from a database, API or network drive to a dataset file with its query record, then read that file back."
scope: scoped
globs:
  - "**/*.py"
applies_if:
  domino_project: true
section: datasets
priority: 43
tags: [python, domino, jobs]
---

# Domino materialized external data

Domino's reproducibility engine records a run's code, environment, project files and dataset snapshots, but not the rows it read from a database, an API, a network drive or a Domino data source. A job that trains or reports on external data first writes the exact extract it uses to a dataset path (Parquet, or CSV with an explicit encoding), records the query, its parameters, the row count and the extraction time beside it, and then reads that file back.

## Bad Example

```python
import pandas as pd


def train(conn: Connection, since: str) -> Model:
    query = f"SELECT * FROM orders WHERE created_at >= '{since}'"  # injectable, unrecorded
    return fit(pd.read_sql(query, conn))  # the rows exist only in memory
```

## Good Example

```python
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ORDERS_QUERY = "SELECT id, amount_cents, created_at FROM orders WHERE created_at >= %(since)s"


def extract_orders(conn: Connection, *, since: date, out_dir: Path) -> Path:
    orders = pd.read_sql(ORDERS_QUERY, conn, params={"since": since})
    data_path = out_dir / "orders.parquet"
    orders.to_parquet(data_path)
    record = {
        "source": "warehouse.orders",
        "query": ORDERS_QUERY,
        "parameters": {"since": since.isoformat()},
        "row_count": len(orders),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "extract.json").write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
    )
    return data_path


def train(ctx: JobContext, conn: Connection, *, since: date) -> Model:
    out_dir = run_dir(ctx.datasets_dir / "extracts", ctx.run_id)
    data_path = extract_orders(conn, since=since, out_dir=out_dir)
    return fit(pd.read_parquet(data_path))  # trains on exactly what was saved
```

## Notes

- Snapshot the extract so later runs can pin it (`domino-dataset-snapshots`); `run_dir` keys it by run (`domino-run-scoped-writes`).
- The documentation advises keeping a result set persisted to project files under 10 GB, so larger extracts go to a dataset (`domino-datasets-for-large-data`).
- A TrainingSet from the python-domino client is an alternative for versioned data frames.
- Queries bind their parameters (`python-parameterized-queries`, python-coding skill); connection credentials come from environment variables (`domino-secrets-in-env-vars`).
- Re-extracting the same partition must stay idempotent (`domino-idempotent-jobs`).
- File I/O passes `encoding="utf-8"` wherever text is written or read.
