# Review signals

What a reviewer or a failing check sees in array and frame code, and the ml-data rule that fixes it. Each row is a signal only; the fix lives in the rule it names, so open that rule before changing the code.

Skip the rows for libraries this repository does not declare. A rule id the skill's Rules index does not list is not active here.

## Constructs in a diff

| Construct | Rule |
| --- | --- |
| A per-value loop, `iterrows`, `itertuples`, `apply(axis=1)`, `map_elements` or `map_rows` computing a column | ml-vectorization |
| `np.append`, `np.concatenate`, `pd.concat`, `pl.concat`, `vstack` or `frame.loc[len(frame)] = row` inside a loop | ml-build-once |
| `inplace=True`; a write into a parameter's slice or mask; `out=` into a parameter; `insert_column` or `extend` on a received frame | ml-data-transforms |
| `frame[mask]["col"] = value` or `frame["col"][mask] = value` | ml-loc-assignment |
| A read with no `dtype=` or `schema_overrides=`; `parse_dates=`; `to_datetime` without `format=` or with `errors="coerce"`; ids read as integers | ml-dtypes-at-load |
| A loader that returns data unchecked, or an `assert` as the check | ml-check-after-load |
| With pandera: one check repeated across functions, or `validate` without `lazy=True` | ml-frame-validation |
| `np.zeros` or `np.empty` without `dtype`; `dtype=object`; narrow integer types for counts | ml-numpy-dtypes |
| `astype("category")` per source, or category lists written inline | ml-categorical-labels |
| `np.random.seed` or legacy `np.random` draws; `random.seed`; `sample`, `shuffle` or a split with no seed or `random_state`; a `DataLoader` shuffling without a generator | ml-seeded-randomness |
| `df1`, `df2`, `df3` intermediates; `query` or `eval` strings | ml-method-chaining |
| `groupby().apply` for a built-in reducer; `agg` followed by renaming or flattening columns | ml-named-aggregation |
| A bare `np.ndarray` or `Any` for arrays and frames; a NumPy scalar returned | ml-array-typing |
| `==` or `(a == b).all()` on float arrays; `pytest.approx` on arrays or frames; expected data read from a golden CSV | ml-numeric-assertions |
| `pickle`, `joblib`, `torch.load`, `np.load`, `read_pickle`, `yaml.load`, `eval` or `exec` on data, `trust_remote_code` | ml-serialization-security (its review checklist names each) |

## Runtime warnings and errors

| Message gist | Library | Rule |
| --- | --- | --- |
| `SettingWithCopyWarning` or `ChainedAssignmentError` | pandas | ml-loc-assignment |
| `DtypeWarning` about mixed column types | pandas | ml-dtypes-at-load |
| A `to_datetime` warning that no format could be inferred | pandas | ml-dtypes-at-load |
| `PerformanceWarning` that a frame is highly fragmented | pandas | ml-build-once |
| A `FutureWarning` about the default of `observed` | pandas | ml-named-aggregation, ml-categorical-labels |
| `PolarsInefficientMapWarning` | polars | ml-vectorization |
| A `RuntimeWarning` about overflow, or counts that wrapped negative | NumPy | ml-numpy-dtypes |
| `ValueError`: the truth value of an array is ambiguous, raised in a test | NumPy, pandas | ml-numeric-assertions |
| A `torch.load` warning or error about `weights_only` | torch | ml-serialization-security |
| `InconsistentVersionWarning` on unpickling an estimator | scikit-learn | ml-serialization-security |
| mypy: missing type parameters for generic type `ndarray`, or pandas objects revealed as `Any` | NumPy, pandas | ml-array-typing |

Never answer the `weights_only` warning with `weights_only=False` on a file from elsewhere: the rule's safe forms replace it.

## Lint codes

These apply only where the repository's ruff selection already includes the code. Adding codes to that selection is the propose-first step of ruff-lint in python-tooling, never part of the fix.

| Code | Rule |
| --- | --- |
| PD002 | ml-data-transforms |
| NPY002 | ml-seeded-randomness |
| S301, S403 | ml-serialization-security |
| S506 | ml-serialization-security (YAML) |
| S307, S102 in data, config or feature-pipeline code | ml-serialization-security (its dispatch note) |

Related guide: library-equivalents.md.
