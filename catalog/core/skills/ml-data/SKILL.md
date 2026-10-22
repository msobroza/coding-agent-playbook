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
---

# ML and data

Conventions for code that loads, stores or transforms models, arrays and data frames, in modules and in notebooks alike. A rule applies only when the repo uses the libraries it covers, and each one renders only the sections for the libraries detected here, so the rules index in this file lists just the ones that apply.

Treat code that loads a model, checkpoint, cache or array from disk or the network as security-sensitive: open the serialization rules first when the index lists them.
