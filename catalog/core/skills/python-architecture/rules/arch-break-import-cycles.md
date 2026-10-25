---
id: arch-break-import-cycles
name: Break import cycles
description: "Break an import cycle by fixing the dependency (invert the wrong-way edge, move the shared type down, or merge), never by hiding the import inside a function."
scope: scoped
globs:
  - "**/*.py"
section: layers
priority: 22
tags: [python, architecture, imports]
---

# Break import cycles by fixing the dependency

## Description

A cycle means neither module can be understood, tested or loaded without the other. Fix the dependency instead of hiding it:

1. Find the edge that points the wrong way (a lower layer importing a higher one) and invert it: the lower module declares a Protocol or takes a `Callable`, and the composition root passes the higher-level implementation in.
2. When both modules need the same type, move that type down into the domain.
3. Two modules that always change together and import each other are one module in two files: merge them.
4. Moving an import into a function body to dodge the cycle only hides it.
5. A cycle that exists only for annotations is legitimately broken with an import under `if TYPE_CHECKING:`.

A cycle across layers is always a wrong-way edge and the first thing to fix. A cycle inside one package usually means a module wants splitting or merging.

## Bad Example

```python
# app/domain/loans.py
def overdue_fee(loan: Loan, today: date) -> int:
    from app.services.lending import FeePolicy  # hidden here to dodge the cycle

    return FeePolicy.standard().fee_for(loan, today)


# app/services/lending.py
from app.domain.loans import Loan, overdue_fee  # the domain imports this module back
```

## Good Example

```python
# app/domain/loans.py: the shared type lives in the domain, and the policy arrives as a parameter
FeeForDays = Callable[[int], int]  # days late -> fee in cents


@dataclass(frozen=True)
class Loan:
    loan_id: int
    due_on: date


def overdue_fee(loan: Loan, today: date, fee_for_days: FeeForDays) -> int:
    days_late = (today - loan.due_on).days
    return fee_for_days(days_late) if days_late > 0 else 0


# app/services/lending.py: imports the domain, never the other way round
from app.domain.loans import Loan, overdue_fee
```

## Notes

- Annotation-only cycles: put the import under `if TYPE_CHECKING:` and add `from __future__ import annotations` (or quote the annotations).
- Function-local imports are fine when they keep an optional or heavy dependency lazy; they still count for the layer rules, but not for import-time cycles.
- The skill's layer_map.py script reports only cycles of imports that run at import time, so a cycle hidden by a function-local import has to be found by reading the code.
- How to write and order imports is the python-coding skill's python-imports rule.
- How to read the script's cycle output and confirm each cycle in the code: see architecture-review.md.
