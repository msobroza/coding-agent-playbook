---
id: ml-data
name: ml-data
description: "Conventions for ML models, arrays and data frames."
playbook:
  use_when: "loading or saving models, or transforming arrays and data frames"
  files: "Model, array and data-frame code"
  sections:
    - id: security
      title: "Serialization Security"
      impact: CRITICAL
      summary: "Treat loading a model, checkpoint, cache or array from elsewhere as a code-execution boundary."
      open_when: "Code loads or saves a model, checkpoint, cache or artifact: pickle, joblib, torch.load, np.load, read_pickle, yaml.load."
    - id: vectorization
      title: "Vectorization"
      impact: CRITICAL
      summary: "Keep computation in compiled array and frame code instead of the Python interpreter."
      open_when: "A loop, iterrows, apply(axis=1) or map_elements computes values one at a time, or an array or frame grows inside a loop."
    - id: mutation
      title: "Indexing & Mutation"
      impact: CRITICAL
      summary: "Write to arrays and frames in ways that are correct under copy-on-write and visible in the data flow."
      open_when: "A function writes into an array or frame it was given: slice or mask assignment, out=, inplace=True, df[m]['col'] = v."
    - id: dtypes
      title: "Dtypes & validation"
      impact: HIGH
      summary: "Make dtypes a decision where data enters, and check columns and dtypes right there."
      open_when: "Data is read in (read_csv, scan_csv, np.loadtxt), an array is created, or a dtype, astype or label column is chosen."
    - id: reproducibility
      title: "Reproducibility"
      impact: HIGH
      summary: "Make runs repeatable with one seeded random source and no hidden global state."
      open_when: "Code draws random numbers (np.random, random, torch), shuffles, samples or splits data, or passes a seed or random_state."
    - id: style
      title: "Chaining style"
      impact: MEDIUM
      summary: "Write frame transformations that read top to bottom as one pipeline."
      open_when: "A frame pipeline is written as reassigned intermediate variables, or a groupby/group_by result is aggregated or renamed."
    - id: typing
      title: "Typing"
      impact: MEDIUM
      summary: "Type hints that carry dtype information for arrays and frames."
      open_when: "A type hint is added or changed for an array or frame parameter or return value (np.ndarray, npt.NDArray, pd.DataFrame)."
    - id: testing
      title: "Testing"
      impact: MEDIUM
      summary: "Assertions that fit floating-point arrays and frames."
      open_when: "A test checks arrays, frames or float results: ==, (a == b).all(), pytest.approx on an array, or a golden CSV."
  references:
    - path: references/library-equivalents.md
      open_when: "Code mixes NumPy, pandas, polars or torch, or ports a data operation from one of them to another."
      applies_if:
        any_ml_stack: ["numpy", "pandas", "polars"]
    - path: references/review-signals.md
      open_when: "Reviewing array or frame code, or fixing a pandas, NumPy, polars or torch warning or a ruff PD, NPY or S finding."
      applies_if:
        any_ml_stack: ["numpy", "pandas", "polars"]
---

# ML and data

Conventions for code that loads, stores or transforms models, arrays and data frames, in modules and in notebooks alike. Numeric code has idioms that differ from general Python: loops are the anti-pattern, arrays and frames are buffers passed around as values, and dtypes are a design decision. Where a rule here overlaps a python-coding rule, this skill wins for array and frame code.

A rule applies only when the repo uses the libraries it covers, and each rule renders only the lines for the libraries detected here, so the rules index in this file lists just the ones that apply. The two navigation references are library-labelled files copied as written: read only the columns and rows of the libraries this repo declares. Treat code that loads a model, checkpoint, cache or array from disk or the network as security-sensitive: open the Serialization Security rules first when the index lists them.

## Quick Reference

### Vectorization

```python
# NumPy: whole-array operations and selects, not loops
too_hot = readings > threshold
tier = np.select([weights >= 20_000, weights >= 5_000], ["freight", "heavy"], default="standard")

# pandas: whole-column operations, not iterrows or apply(axis=1)
parcels = parcels.assign(
    volume_cm3=parcels["length_cm"] * parcels["width_cm"] * parcels["height_cm"]
)

# polars: expressions, not map_elements
parcels = parcels.with_columns(
    pl.when(pl.col("weight_g") >= 20_000)
    .then(pl.lit("freight"))
    .otherwise(pl.lit("standard"))
    .alias("tier")
)

# Any library: collect the pieces, then build once
frames = [pd.read_csv(path, dtype=READING_DTYPES) for path in paths]
readings = pd.concat(frames, ignore_index=True)
```

### Indexing & Mutation

```python
# pandas: one .loc in one step; chained assignment never reaches the frame under copy-on-write
shipments.loc[shipments["status"] == "pending", "priority"] = "high"

# pandas: the returning form, rebound, not inplace=True
shipments = shipments.dropna(subset=["destination"]).sort_values("created_at")

# NumPy: compute a new array instead of writing into the one the function received
clipped = np.minimum(readings, ceiling)
```

### Dtypes & validation

```python
# pandas: declare types where data enters, parse dates with an exact format
shipments = pd.read_csv(
    path,
    dtype={"customer_id": "string", "weight_g": "Int64", "region": REGION},
    usecols=["customer_id", "weight_g", "region", "created_at"],
).assign(created_at=lambda frame: pd.to_datetime(frame["created_at"], format=DATE_FORMAT))
SEVERITY = pd.CategoricalDtype(["low", "medium", "high"], ordered=True)

# NumPy: every created array names its dtype
embeddings = np.zeros((n_items, 768), dtype=np.float32)
```

### Reproducibility

```python
# NumPy: one generator from the run's seed, passed down as a parameter
def run_experiment(seed: int) -> ExperimentResult:
    rng = np.random.default_rng(seed)
    split_rng, noise_rng = rng.spawn(2)
    ...


def add_noise(values: npt.NDArray[np.float64], rng: np.random.Generator) -> npt.NDArray[np.float64]:
    return values + rng.normal(scale=0.1, size=values.shape)
```

### Chaining style

```python
# pandas: one pipeline that reads top to bottom, with named aggregation
monthly = (
    shipments.assign(month=lambda frame: frame["created_at"].dt.to_period("M"))
    .loc[lambda frame: frame["weight_g"] > 0]
    .groupby("month", as_index=False, observed=True)
    .agg(total_weight_g=("weight_g", "sum"), shipments=("shipment_id", "count"))
)

# polars: a lazy scan, collected once
monthly = (
    pl.scan_csv(path, schema_overrides=SHIPMENT_SCHEMA)
    .with_columns(pl.col("created_at").dt.truncate("1mo").alias("month"))
    .filter(pl.col("weight_g") > 0)
    .group_by("month")
    .agg(pl.col("weight_g").sum().alias("total_weight_g"))
    .collect()
)
```

### Typing

```python
# NumPy: accept anything array-like, return a precise array type
def to_float32(values: npt.ArrayLike) -> npt.NDArray[np.float32]:
    return np.asarray(values, dtype=np.float32)
```

### Testing

```python
# NumPy: tolerance-aware comparison of float arrays
np.testing.assert_allclose(result, expected, rtol=1e-6, atol=1e-12)

# pandas: frame comparison that checks the index, dtypes and column order too
pd.testing.assert_frame_equal(result_frame, expected_frame)

# polars: its testing module is imported on its own; it checks dtypes and order too
import polars.testing

polars.testing.assert_frame_equal(result_frame, expected_frame)
```

## See Also

- python-coding: general Python conventions; its argument-mutation, typing and validation rules have direct counterparts here.
- python-testing: test structure, fixtures and test doubles that numeric tests still follow.
