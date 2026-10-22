---
id: ml-numpy-dtypes
name: NumPy dtypes
description: "Choose NumPy dtypes on purpose: state them at creation and at function entry, give integers headroom, use float32 for features and float64 for statistics, and avoid dtype=object."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "**/*.ipynb"
applies_if:
  any_ml_stack: ["numpy"]
section: dtypes
priority: 43
tags: [ml, numpy, dtypes]
---

# Choose NumPy dtypes explicitly

## Description

NumPy picks a dtype from the input when you do not say otherwise: `np.array([1, 2])` is `int64`, `np.zeros(n)` is `float64`, and values read from files or other libraries can arrive as `int32`, `uint8` or `float16`. Fixed-width integers wrap around silently on overflow, and mixing widths promotes in ways that are easy to misjudge. State the dtype at construction and at the boundary where data enters, and check it in tests.

## Bad Example

```python
import numpy as np

pixels = load_image()  # uint8 from the decoder
brightness = pixels + 100  # wraps: 200 + 100 -> 44

counts = np.array(histogram, dtype=np.int32)
total = counts * 1_000_000  # overflows silently past 2**31

embeddings = np.zeros((n, 768))  # float64, twice the memory the model needs

ids = np.array(raw_ids)  # int64? object? depends on the input
```

## Good Example

```python
import numpy as np

pixels = load_image().astype(np.int16)  # widen before arithmetic
brightness = np.clip(pixels + 100, 0, 255).astype(np.uint8)

counts = np.asarray(histogram, dtype=np.int64)
total = counts * 1_000_000

embeddings = np.zeros((n, 768), dtype=np.float32)

ids = np.asarray(raw_ids, dtype=np.int64)
```

## Notes

- Overflow on NumPy integer arrays does not raise; it wraps. Scalar operations may warn, array operations do not. Pick a width with headroom for the largest value the data can reach, such as `int64` for counts and for amounts in cents.
- A Python scalar adapts to the array's dtype (`uint8_array + 100` stays `uint8`), so the wraparound in the bad example is exactly what happens.
- `float32` is usually enough for model features and halves memory and bandwidth; keep `float64` for sums, means and other statistics, where rounding error accumulates.
- Use `np.asarray(values, dtype=...)` at function entry to normalize inputs from lists, other libraries or frames; it avoids a copy when the dtype already matches.
- Avoid `dtype=object` arrays: they hold Python objects, so every operation falls back to a Python loop. One usually means ragged or mixed data that should be modeled differently.
- Checking the dtype and shape of an array that was just loaded is `ml-check-after-load`, with an error raised, not an `assert`.
