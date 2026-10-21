---
id: ml-data
name: ml-data
description: "Conventions for ML models and for array and data-frame code."
playbook:
  use_when: "loading or saving models, or transforming arrays and data frames"
  files: "Model, array and data-frame code"
---

# ML and data

Conventions for code that loads, stores or transforms models, arrays and data frames, in modules and in notebooks alike. A rule applies only when the repo uses the libraries it covers, and each one renders only the sections for the libraries detected here, so the rules index in this file lists just the ones that apply, each with the one line it requires.

## Picking rules

Open every rule whose line matches the change and read it in full before writing code. Treat code that loads a model, checkpoint, cache or array from disk or the network as security-sensitive: open the serialization rule first when the index lists it.

- Loading or saving a model, checkpoint, cache or pickled artifact: serialization.
- A loop over array values or frame rows, or an array or frame built up step by step: vectorization.
- A function that changes an array or frame, a pandas assignment, a pipeline or an aggregation: data transforms.
- Reading data, choosing dtypes, label columns or annotating arrays: dtypes and typing.
- Random numbers, seeds, or tests that compare arrays and frames: reproducibility and numeric tests.
