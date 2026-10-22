# Library equivalents

One data operation per row, written as call names only in NumPy, pandas, polars and torch. The reasons and the examples live in the rule named in the last column; open it before writing the code.

## Reading the tables

- Columns: NumPy | pandas | polars | torch | rule. Read only the columns of the libraries this repository declares.
- A rule id is active here when this skill's Rules index lists it; an id the index does not list means the repository lacks that rule's libraries. The index lists ml-serialization-security only when a model library is declared.
- A dash means the library has no idiom for the operation, or no ml-data rule covers it there.
- The torch cells matter when torch sits next to NumPy, pandas or polars, for example when a feature frame becomes a tensor.
- A function with no whole-column form climbs the ml-vectorization ladder in every library; the rungs and where to stop are in that rule.

## Compute over whole columns

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| Arithmetic and comparisons | operators, ufuncs | operators on Series | `pl.col` expressions | operators on tensors | ml-vectorization |
| Two-way select | `np.where` | `Series.where`, `Series.mask` | `pl.when().then().otherwise()` | `torch.where` | ml-vectorization |
| Many-way select | `np.select` | `np.select` on Series | nested `pl.when` chain | nested `torch.where` | ml-vectorization |
| Reduce along an axis or column | `sum(axis=)`, `mean(axis=)` | `sum()`, `mean()`, `axis=` | `pl.col().sum()` | `sum(dim=)`, `mean(dim=)` | ml-vectorization |
| Text and date parts | - | `.str`, `.dt` accessors | `.str`, `.dt` namespaces | - | ml-vectorization |

## Build results once

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| Gather pieces, then build once | `np.concatenate`, `np.stack` | `pd.DataFrame(rows)`, `pd.concat` | `pl.concat` | `torch.stack`, `torch.cat` | ml-build-once |
| Preallocate with a dtype | `np.empty(shape, dtype=)` | - | - | `torch.empty(shape, dtype=)` | ml-build-once |
| Draw all random values in one call | `rng.normal(size=n)` | - | - | `torch.randn(n, generator=g)` | ml-build-once |

## Write without touching the caller's data

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| Return a new result | `np.minimum`, `np.clip` | `assign`, returning methods | `with_columns` | `torch.clamp` | ml-data-transforms |
| Conditional write on an object the function created | mask assignment after `.copy()` | `.loc[mask, col] = value` | `pl.when` inside `with_columns` | mask assignment after `.clone()` | ml-data-transforms, ml-loc-assignment |
| In-place forms, kept for the function's own objects | `out=` | - | `insert_column`, `extend` | trailing-underscore methods | ml-data-transforms |

## Types where data enters

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| Read with declared columns and types | `np.loadtxt(dtype=, usecols=)` | `read_csv(dtype=, usecols=)` | `pl.read_csv(schema_overrides=, columns=)` | `torch.as_tensor(dtype=)` | ml-dtypes-at-load |
| Parse dates with an exact format | - | `pd.to_datetime(format=, errors="raise")` | `.str.to_datetime(format=, strict=True)` | - | ml-dtypes-at-load |
| Ids with leading zeros | read as `str` | `"string"` dtype | `pl.String` | - | ml-dtypes-at-load |
| Nullable integers | - | `"Int64"` | every column is nullable | - | ml-dtypes-at-load |
| Creation and entry dtypes | `np.zeros(dtype=)`, `np.asarray(dtype=)` | - | - | `torch.zeros(dtype=)` | ml-numpy-dtypes |
| Label columns | none | one `pd.CategoricalDtype` constant | one `pl.Enum` constant | none | ml-categorical-labels |

## Check after loading

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| Check dtype and shape, raise naming actual and expected | `array.dtype`, `array.shape` | `frame.dtypes` | `frame.schema` | `tensor.dtype`, `tensor.shape` | ml-check-after-load |
| One schema, where the repository already has pandera | - | `pandera.pandas`, `validate(lazy=True)` | `pandera.polars`, `validate(lazy=True)` | - | ml-frame-validation |

## Seeded randomness

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| One generator from the run's seed | `np.random.default_rng(seed)` | the NumPy generator | `random.Random(seed)` | `torch.manual_seed(seed)` | ml-seeded-randomness |
| Pass it down | a `Generator` parameter | a `Generator` parameter | a `Random` parameter | a `torch.Generator` parameter | ml-seeded-randomness |
| Sample or shuffle rows | `rng.permutation` | `frame.sample(random_state=rng)` | `frame.sample(seed=)` | `torch.randperm(n, generator=g)` | ml-seeded-randomness |
| Per-worker children | `rng.spawn`, `SeedSequence(seed).spawn` | - | - | - | ml-seeded-randomness |
| Library-held state | scikit-learn `random_state` drawn from `rng` | - | - | a `torch.Generator` per `DataLoader` | ml-seeded-randomness |

## Group and chain

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| Named aggregation | - | `agg(name=(col, func))` | `group_by().agg(expr.alias())` | - | ml-named-aggregation |
| Broadcast a group result back to rows | - | `transform` | `expr.over()` | - | ml-named-aggregation |
| Categorical group keys | - | `observed=True` | nothing needed | - | ml-named-aggregation, ml-categorical-labels |
| One pipeline | - | `assign`, `.loc[lambda]`, `pipe` | lazy scan, then `collect()` once | - | ml-method-chaining |

## Annotate

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| Array and frame parameters and returns | `npt.ArrayLike` in, `npt.NDArray[np.float64]` out | `pd.DataFrame`, columns in the docstring, pandas-stubs | `pl.DataFrame` (python-typing applies) | `torch.Tensor` (python-typing applies) | ml-array-typing |
| Scalar results | returned as Python `float` | returned as Python `float` | - | - | ml-array-typing |

## Assert in tests

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| Float arrays | `np.testing.assert_allclose` with `atol` near zero | - | - | `torch.testing.assert_close` | ml-numeric-assertions |
| Exact arrays | `np.testing.assert_array_equal` | - | - | - | ml-numeric-assertions |
| Frames and series | - | `pd.testing.assert_frame_equal`, `assert_series_equal` | `polars.testing.assert_frame_equal`, `assert_series_equal` | - | ml-numeric-assertions |
| Scalars | `pytest.approx` (pytest-assertions in python-testing) | same | same | same | - |

## Save and load

| Operation | NumPy | pandas | polars | torch | Rule |
| --- | --- | --- | --- | --- | --- |
| Arrays | `np.save`; `np.load(allow_pickle=False)` | - | - | - | ml-serialization-security |
| Frames | - | Parquet where the repository has an engine; never `read_pickle` on a file from elsewhere | Parquet | - | ml-serialization-security |
| Model weights | - | - | - | `state_dict` with `torch.load(weights_only=True)`; safetensors where the repository has it | ml-serialization-security |

Related guide: review-signals.md.
