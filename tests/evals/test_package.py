"""Smoke test for the ``coding_agent_playbook.evals`` public surface.

The package ``__init__`` is a docstring only (L5): overlay authors and tooling
import each public name from its defining module, and these tests pin that
those modules still define them.
"""

from __future__ import annotations


def test_eval_sample_dataclasses_live_in_the_sample_module() -> None:
    from coding_agent_playbook.evals import sample as sample_mod

    assert sample_mod.EvalSample.__module__ == sample_mod.__name__
    assert sample_mod.SampleSetup.__module__ == sample_mod.__name__
    assert sample_mod.SampleInvocation.__module__ == sample_mod.__name__
    assert sample_mod.Layer.__module__ == sample_mod.__name__


def test_loader_and_validator_define_their_entry_points() -> None:
    from coding_agent_playbook.evals import loader as loader_mod
    from coding_agent_playbook.evals import validator as validator_mod

    assert loader_mod.load_eval_sample_from_dir.__module__ == loader_mod.__name__
    assert loader_mod.discover_eval_sample_dirs.__module__ == loader_mod.__name__
    assert validator_mod.validate_samples.__module__ == validator_mod.__name__
    assert validator_mod.EvalValidationError.__module__ == validator_mod.__name__


def test_package_root_exports_no_names() -> None:
    from coding_agent_playbook import evals as pkg

    assert not hasattr(pkg, "__all__")
    assert not hasattr(pkg, "EvalSample")
