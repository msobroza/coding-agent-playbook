---
id: python-imports
name: Imports
description: "Group imports as standard library, third-party, first-party; import names explicitly, never with import *; relative imports only inside one package."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: idioms
priority: 73
tags: [python, style, imports]
---

# Import names explicitly, in three groups

## Description

The import block is the map of a module's dependencies: a reader, a refactoring tool or a search should learn from it where every name comes from. Group imports in this order, with a blank line between groups: standard library, third-party, then first-party (this repo's packages). Never write `from module import *`; name what you use. A wildcard hides where a name comes from, lets a later import silently overwrite an earlier one, and makes a rename unsafe because no line shows who depends on the name.

## Bad Example

```python
# inside contracts/operations.py
from models import *  # which names? from which file?
from random import *

from ..customers.models import Customer  # relative import across top-level packages
```

## Good Example

```python
# inside contracts/operations.py
import json  # standard library
from pathlib import Path

import httpx  # third-party

from customers.models import Customer  # first-party, another package: absolute
from .models import Contract  # first-party, the same package: relative is fine
```

## Notes

- Import across packages with the absolute path from the project root. A relative import (`from .models import Contract`) is for a sibling module inside one package; one that climbs out of the top-level package fails with `ImportError`.
- Default to `from package.module import Name`. Use `import package.module` when you use many of its names and the qualified name reads better.
- Alias an import only for a widely known convention (`import numpy as np`, `import pandas as pd`) or a name that is too long; a private alias for a short name only hides it.
- The order inside each group follows the repo's formatter and its isort settings (see ruff-format in the python-tooling skill); don't sort by hand against them.
- An import cycle is not fixed by moving the import into a function: move the shared dependency so the cycle disappears (arch-break-import-cycles in the python-architecture skill).
