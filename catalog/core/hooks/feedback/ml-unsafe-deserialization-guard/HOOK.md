---
id: ml-unsafe-deserialization-guard
name: ML unsafe deserialization guard
description: Deny an edit that adds pickle-based loads or other unsafe deserialization to Python code or notebook cells; flag version-dependent loads and code-executing calls.
tier: default
priority: 40
events: [pre_tool_use]
linked_rule: ml-serialization-security
matcher:
  pre_tool_use:
    tools: [edit, write, notebook_edit]
    paths: ["**/*.py", "**/*.ipynb"]
handler:
  builtin: deser_sink_guard
  config:
    block:
      - {call: pickle.load, advice: "Load a data-only format instead: safetensors, JSON, Parquet or .npy without pickle."}
      - {call: pickle.loads, advice: "Load a data-only format instead: safetensors, JSON, Parquet or .npy without pickle."}
      - {call: dill.load, advice: "Load a data-only format instead: safetensors, JSON, Parquet or .npy without pickle."}
      - {call: dill.loads, advice: "Load a data-only format instead: safetensors, JSON, Parquet or .npy without pickle."}
      - {call: shelve.open, advice: "Store the data in a data-only format (JSON, SQLite) instead of a pickle-backed shelf."}
      - {call: joblib.load, advice: "Load a data-only format instead: skops, ONNX, safetensors or JSON parameters."}
      - {call: pandas.read_pickle, advice: "Read Parquet, CSV or Feather instead of a pickled DataFrame."}
      - {call: yaml.load, unless: {Loader: [SafeLoader, CSafeLoader]}, advice: "Use yaml.safe_load(...), or pass Loader=yaml.SafeLoader."}
      - {call: torch.load, kwarg: {weights_only: false}, advice: "Use torch.load(..., weights_only=True), or store the weights as safetensors."}
      - {call: numpy.load, kwarg: {allow_pickle: true}, advice: "Keep allow_pickle=False and save object data in a data-only format."}
      - {call: "*", kwarg: {trust_remote_code: true}, advice: "Drop trust_remote_code=True: it runs Python code shipped in the model repository."}
    warn:
      - {call: torch.load, missing: [weights_only], advice: "Pass weights_only=True: the default depends on the installed torch version."}
      - {call: numpy.load, missing: [allow_pickle], advice: "Pass allow_pickle=False: the default depends on the installed numpy version."}
      - {call: "*.from_pretrained", missing: [revision], advice: "Pin revision= to a reviewed commit: a moving hub ref can swap the weights or the code."}
      - {call: eval, advice: "eval runs arbitrary code: make sure its input can never come from outside."}
      - {call: exec, advice: "exec runs arbitrary code: make sure its input can never come from outside."}
      - {call: os.system, advice: "Use subprocess.run([...]) with an argument list: a shell string invites injection."}
      - {call: "subprocess.*", kwarg: {shell: true}, advice: "Pass an argument list without shell=True: a shell string invites injection."}
decisions: [deny, ask, context, none]
timeout: 2
on_error: ask
supports: [claude_code, opencode]
tags: [feedback, ml, security]
---
