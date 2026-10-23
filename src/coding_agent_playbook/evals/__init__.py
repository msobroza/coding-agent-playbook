"""Eval samples: the sample schema, its loader and validator, and how a sample is run and graded (SPEC §15).

Deliberately empty: import the defining module (``evals.sample`` for ``EvalSample``,
``SampleSetup``, ``SampleInvocation`` and ``Layer``; ``evals.loader`` for
``load_eval_sample_from_dir`` and ``discover_eval_sample_dirs``; ``evals.validator``
for ``validate_samples`` and ``EvalValidationError``). ``compile/`` turns a sample's
gate, rubric and aggregate blocks into grading-kernel checks, and ``run/`` runs a
sample against a harness and scores the result. ``evals.comparison`` compares a
base ref's runs with HEAD's (the opt-in ``playbook eval --compare``, D37).
"""
