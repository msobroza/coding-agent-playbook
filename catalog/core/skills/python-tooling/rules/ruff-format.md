---
id: ruff-format
name: Formatting with ruff
description: "Let the configured formatter own layout and the configured sorter own import order; format only the files you changed and never hand-align."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "**/*.pyi"
  - "pyproject.toml"
  - "ruff.toml"
  - ".ruff.toml"
section: formatting
priority: 41
tags: [python, tooling, ruff]
---

# Formatting with ruff

## Description

Ruff's formatter is a drop-in replacement for Black. Combined with the isort rules, it handles both code formatting and import organization in one tool. The formatter owns layout: never hand-align columns, rewrap lines your own way or undo a format run; when a construct formats badly, restructure the code instead.

## Bad Example

Imports ordered by hand, which the I rules flag (I001):

```python
from invoicing.totals import order_total
import sys
from pydantic import BaseModel
import os
```

Assignments aligned by hand, which every format run undoes, as `ruff format --diff` shows:

```diff
-TAX_RATE      = Decimal("0.20")
-SHIPPING_FEE  = Decimal("4.90")
+TAX_RATE = Decimal("0.20")
+SHIPPING_FEE = Decimal("4.90")
```

## Good Example

The sorter's output, with the repo's isort settings:

```python
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from invoicing.core import service
from invoicing.totals import order_total

if TYPE_CHECKING:
    from invoicing.models import Customer
```

```bash
ruff format --check .            # as CI runs it
ruff format --diff .             # show what would change
ruff format src/invoicing/totals.py  # only the files you changed
ruff check --select I --fix src/invoicing/totals.py  # sort imports with the configured settings
```

## Notes

- The style is Black-compatible; where Black is the configured formatter, the same rules hold.
- Line length, quote style and the isort settings are the repo's. `known-first-party` is usually detected from the project layout.
- Format only the files you changed: files outside the change are not reformatted, as the post-edit format hook also does.
- A mismatch between the lint and format line lengths, or a lint rule ruff says conflicts with the formatter, is reported to the user, not edited.
- Never add formatter settings unasked.
- The grouping convention itself (standard library, third-party, first-party) is python-imports' and the quote convention python-idioms', both in the python-coding skill; this rule lets the configured formatter and sorter apply them.
