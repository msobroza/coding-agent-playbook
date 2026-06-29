"""Smoke test for the ``coding_agent_playbook.evals`` package surface.

Confirms the public API (everything overlay authors should import)
re-exports cleanly from the package root and refers to the same classes as
the submodules.
"""

from __future__ import annotations


def test_eval_task_public_re_export_matches_module() -> None:
    from coding_agent_playbook import evals as pkg
    from coding_agent_playbook.evals import task as task_mod

    assert pkg.EvalTask is task_mod.EvalTask
    assert pkg.TaskSetup is task_mod.TaskSetup
    assert pkg.TaskInvocation is task_mod.TaskInvocation
    assert pkg.Layer is task_mod.Layer


def test_loader_and_validator_re_exports() -> None:
    from coding_agent_playbook import evals as pkg
    from coding_agent_playbook.evals import loader as loader_mod
    from coding_agent_playbook.evals import validator as validator_mod

    assert pkg.load_eval_task_from_dir is loader_mod.load_eval_task_from_dir
    assert pkg.discover_eval_task_dirs is loader_mod.discover_eval_task_dirs
    assert pkg.validate_tasks is validator_mod.validate_tasks
    assert pkg.EvalValidationError is validator_mod.EvalValidationError


def test_all_lists_every_public_name() -> None:
    from coding_agent_playbook import evals as pkg

    expected = {
        "EvalTask",
        "EvalValidationError",
        "Layer",
        "TaskInvocation",
        "TaskSetup",
        "discover_eval_task_dirs",
        "load_eval_task_from_dir",
        "validate_tasks",
    }
    assert set(pkg.__all__) == expected
