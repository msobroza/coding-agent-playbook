"""Eval tasks: the task schema, its loader and validator, and how a task is run and graded (SPEC §15).

Deliberately empty: import the defining module (``evals.task`` for ``EvalTask``,
``TaskSetup``, ``TaskInvocation`` and ``Layer``; ``evals.loader`` for
``load_eval_task_from_dir`` and ``discover_eval_task_dirs``; ``evals.validator``
for ``validate_tasks`` and ``EvalValidationError``). ``compile/`` turns a task's
gate, rubric and aggregate blocks into grading-kernel checks, and ``run/`` runs a
task against a harness and scores the result.
"""
