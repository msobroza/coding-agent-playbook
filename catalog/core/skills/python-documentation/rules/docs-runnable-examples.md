---
id: docs-runnable-examples
name: Runnable examples
description: "Make every doc example self-contained with deterministic output, and run it (through the repo's doctest command where one exists) after editing it."
version: 1
scope: scoped
globs:
  - "README*"
  - "docs/**"
  - "examples/**"
  - "*.rst"
section: in-sync
priority: 41
tags: [python, docs, doctest]
---

# Examples run as written

## Description

Readers copy examples before they read prose, and an example that runs is also a test: in numerical code it catches results that are silently wrong. A code example in the README, a docs page, examples/ or a docstring imports what it uses, builds its own inputs and shows the output it really prints. That output is deterministic: randomness is seeded, mappings and sets are sorted, floats are rounded, and NumPy scalars are converted to Python numbers so their repr does not change between versions.

Where the repo already collects doctests (`--doctest-modules` or `--doctest-glob` in its pytest addopts, `doctest_optionflags`, the Sphinx doctest builder, a doctest plugin, a nox or tox session), run that command after editing an example and fix every failure. Where it has none, run the snippet once by hand before finishing. Never add a doctest runner, switch on collection, or turn every example block into `>>>` sessions unasked; whether a docstring carries an example at all is the python-docstrings rule's call (python-coding skill).

## Bad Example

A README quick start that uses a name it never defines and prints a dict whose order and digits vary:

```python
report = summarize(load_orders("orders.csv"))
print(report)
# {'mean': 12.333333333333334, 'max': 20.0, 'min': 4.0}
```

A docstring whose expected output depends on the NumPy version:

```python
def mean_fee(fees: np.ndarray) -> float:
    """Return the mean fee.

    >>> mean_fee(np.array([0.1, 0.1]))
    0.1
    """
    return fees.mean()
```

## Good Example

```python
from orders import load_orders, summarize

report = summarize(load_orders("examples/orders.csv"))
print(sorted(report.items()))
# [('max', 20.0), ('mean', 12.333), ('min', 4.0)]
```

```python
def mean_fee(fees: np.ndarray) -> float:
    """Return the mean fee, rounded to three places.

    >>> mean_fee(np.array([0.1, 0.1]))
    0.1
    >>> mean_fee(fetch_fees("https://fees.example.com"))  # doctest: +SKIP
    """
    # Python float, so the repr reads 0.1 on every NumPy version.
    return round(float(fees.mean()), 3)
```

The skipped line needs the network, so the runner skips it; say why next to every skip.

## Notes

- pytest's flags are `--doctest-modules` and `--doctest-glob`; the repo's configuration decides whether they run.
- The docs check parses Python blocks in changed Markdown and runs doctests only where the pytest configuration already collects them (`docs-check-in-ci`), so an example outside both still needs its one manual run.
- Tolerance comes from the repo's option flags (ELLIPSIS, NORMALIZE_WHITESPACE) or its doctest plugin, never from vague expected output.
- An example that needs a GPU, credentials or slow I/O is skipped with the runner's directive, never deleted.
- Hosts in examples are reserved names only (example.com, .test, localhost).
