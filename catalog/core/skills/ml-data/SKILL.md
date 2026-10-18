---
id: ml-data
name: ml-data
description: "Conventions for handling models and data artifacts in ML code."
playbook:
  use_when: "loading or saving models, checkpoints, caches or any pickled artifact"
  files: "Code that loads or saves models, checkpoints or caches"
---

# ML and data

Conventions for code that loads, stores or transforms models and data. A reference applies only when the repo uses the libraries it covers, so the references index in this file lists just the ones detected here, each with the one line it requires.

## Picking references

Open every reference whose line matches the change and read it in full before writing code. Treat code that loads a model, checkpoint, cache or array from disk or the network as security-sensitive: open the serialization reference first when the index lists it.
