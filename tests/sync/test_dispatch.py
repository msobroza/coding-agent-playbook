"""Hook dispatch and lockfile stamping in ``sync/_dispatch.py`` (prK §C.1.3, §B.6).

Every adapter is told the real repo (the input root) and the prior lockfile
before any write, receives hooks after skills and before ``finalize``, and
hands back its scoped lock entries. ``build_lockfile`` never gives a co-owned
file a whole-file entry, and records the exec bit of copied hook scripts.
"""

from __future__ import annotations

import dataclasses
import errno
import os
import random
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.shared_skills import SharedSkillsAdapter
from coding_agent_playbook.config.tables.hooks import HooksConfig
from coding_agent_playbook.lockfile.model import LockEntry, Lockfile, Provenance, compute_hash
from coding_agent_playbook.sync._dispatch import (
    HookDispatch,
    _skill_write_provenance,
    build_lockfile,
    dispatch_to_adapters,
    real_written_paths,
)
from tests.generated_output.link_zoo import (
    build_link_zoo,
    link_zoo_queries,
    random_link_tree,
    random_tree_queries,
    relink_directory,
    relinkable_outputs,
)
from tests.hook_samples import resolved_hook
from tests.member_skill_samples import sample_member_reference, sample_member_skill

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook
    from coding_agent_playbook.lockfile.model import ProvenanceKind

_SCOPED = LockEntry(
    path=".claude/settings.json",
    sha256="41ab",
    bytes=212,
    kind="runtime",
    artifact_id="registration:pre_tool_use",
    adapter="claude_code",
    scope="json:/hooks/PreToolUse",
)


class FakeHookAdapter(Adapter):
    """Records the order of its calls; writes ``guardrail-<id>.md`` per hook."""

    name = "fake_hooks"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.began: tuple[Path, Lockfile | None, HooksConfig | None] | None = None

    def begin_sync(
        self,
        repo_root: Path,
        prior_lock: Lockfile | None,
        *,
        hooks_config: HooksConfig | None = None,
    ) -> None:
        self.calls.append("begin_sync")
        self.began = (repo_root, prior_lock, hooks_config)

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        self.calls.append("write_rule")
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        self.calls.append("write_prompt")
        return []

    def write_hook(self, hook: ResolvedHook, repo_root: Path) -> list[Path]:
        self.calls.append(f"write_hook:{hook.id}")
        target = repo_root / f"guardrail-{hook.id}.md"
        target.write_text("advice\n", encoding="utf-8")
        return [target]

    def finalize(self, repo_root: Path) -> list[Path]:
        self.calls.append("finalize")
        return []

    def managed_lock_entries(self) -> list[LockEntry]:
        self.calls.append("managed_lock_entries")
        return [_SCOPED]


def _dispatch(tmp_path: Path, adapter: FakeHookAdapter, prior: Lockfile | None) -> list[str]:
    hooks = [resolved_hook("guard-a"), resolved_hook("guard-b", source_package="acme")]
    config = HooksConfig(enabled=True)
    recorder = dispatch_to_adapters(
        {"fake_hooks": adapter},
        [],
        [],
        [],
        tmp_path / "out",
        hooks=HookDispatch(hooks, tmp_path / "repo", prior, config),
    )
    assert adapter.began == (tmp_path / "repo", prior, config)
    assert recorder.managed == [_SCOPED]
    return [str(path.relative_to(tmp_path / "out")) for path in recorder.written]


def test_dispatch_begins_with_the_input_root_and_routes_hooks_before_finalize(
    tmp_path: Path,
) -> None:
    (tmp_path / "out").mkdir()
    adapter = FakeHookAdapter()
    prior = Lockfile(2, "0.2.0", "2026-10-14T00:00:00Z", [])

    written = _dispatch(tmp_path, adapter, prior)

    assert written == ["guardrail-guard-a.md", "guardrail-guard-b.md"]
    assert adapter.calls == [
        "begin_sync",
        "write_hook:guard-a",
        "write_hook:guard-b",
        "finalize",
        "managed_lock_entries",
    ]


def test_dispatch_records_hook_provenance(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    adapter = FakeHookAdapter()
    recorder = dispatch_to_adapters(
        {"fake_hooks": adapter},
        [],
        [],
        [],
        tmp_path / "out",
        hooks=HookDispatch([resolved_hook("guard-b", source_package="acme")]),
    )

    [path] = recorder.written
    assert recorder.provenance[path.resolve()] == Provenance(
        kind="hook", artifact_id="guard-b", source="acme", adapter="fake_hooks"
    )
    assert adapter.began is not None and adapter.began[0] == tmp_path / "out"


class FakeRuntimeAdapter(Adapter):
    """``finalize`` writes one declared runtime file (a shim) and one composed file."""

    name = "fake_runtime"
    runtime_outputs = ("plugins/shim.js",)

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        return []

    def finalize(self, repo_root: Path) -> list[Path]:
        written = [repo_root / "plugins" / "shim.js", repo_root / "COMPOSED.md"]
        for path in written:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
        return written


class FakeSkillRootsAdapter(FakeRuntimeAdapter):
    """Records the native skill roots the dispatch announces, and when."""

    name = "fake_roots"

    def __init__(self) -> None:
        self.calls: list[tuple[str, frozenset[str] | None]] = []

    def note_native_skill_roots(self, roots: frozenset[str]) -> None:
        self.calls.append(("note_native_skill_roots", roots))

    def begin_sync(
        self,
        repo_root: Path,
        prior_lock: Lockfile | None,
        *,
        hooks_config: HooksConfig | None = None,
    ) -> None:
        self.calls.append(("begin_sync", None))


def test_dispatch_tells_every_adapter_the_enabled_native_skill_roots_first(
    tmp_path: Path,
) -> None:
    """C7: agents_md keeps its Where map only when some enabled adapter writes skills."""
    adapter = FakeSkillRootsAdapter()

    dispatch_to_adapters(
        {"fake_roots": adapter, "shared_skills": SharedSkillsAdapter()}, [], [], [], tmp_path
    )

    assert adapter.calls == [
        ("note_native_skill_roots", frozenset({".agents/skills"})),
        ("begin_sync", None),
    ]


def test_dispatch_announces_no_native_skill_root_without_a_skill_adapter(tmp_path: Path) -> None:
    adapter = FakeSkillRootsAdapter()

    dispatch_to_adapters({"fake_roots": adapter}, [], [], [], tmp_path)

    assert adapter.calls[0] == ("note_native_skill_roots", frozenset())


def test_dispatch_tags_declared_runtime_outputs_runtime_and_the_rest_composite(
    tmp_path: Path,
) -> None:
    assert Adapter.runtime_outputs == ()
    recorder = dispatch_to_adapters({"fake_runtime": FakeRuntimeAdapter()}, [], [], [], tmp_path)

    shim, composed = recorder.written
    # §B.6: the shim (like the launcher) is runtime plumbing, not a composed artifact.
    assert recorder.provenance[shim.resolve()] == Provenance(kind="runtime", adapter="fake_runtime")
    assert recorder.provenance[composed.resolve()] == Provenance(
        kind="composite", adapter="fake_runtime"
    )


def test_build_lockfile_skips_shared_outputs_without_scoped_entries(tmp_path: Path) -> None:
    # The last managed element was removed: settings.json was rewritten, but it is
    # co-owned, so a whole-file entry would let the leftover policy delete it later.
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text("{}\n", encoding="utf-8")

    lockfile = build_lockfile(
        [settings],
        tmp_path,
        "0.2.0",
        provenance={settings.resolve(): Provenance(kind="composite", adapter="claude_code")},
        shared=frozenset({".claude/settings.json"}),
    )

    assert lockfile.entries == []


_TYPING = sample_member_reference("python-typing", source_package="acme_overlay")


def test_skill_write_provenance_gives_member_references_their_rules_provenance(
    tmp_path: Path,
) -> None:
    """E9: guard-generated-outputs then points an editor at the rule, the real source."""
    skill_dir = tmp_path / ".claude" / "skills" / "python-coding"
    skill_md, guide, typing_ref = (
        skill_dir / "SKILL.md",
        skill_dir / "references" / "guide.md",
        skill_dir / "rules" / "python-typing.md",
    )

    groups = _skill_write_provenance(
        [skill_md, guide, typing_ref], sample_member_skill("python-coding", _TYPING), "opencode"
    )

    skill_origin = Provenance(
        kind="skill",
        artifact_id="python-coding",
        source="coding_agent_playbook",
        adapter="opencode",
    )
    rule_origin = Provenance(
        kind="rule", artifact_id="python-typing", source="acme_overlay", adapter="opencode"
    )
    assert groups == [([skill_md, guide], skill_origin), ([typing_ref], rule_origin)]


@pytest.mark.parametrize(
    "rel",
    [
        "python-coding/scripts/python-typing.md",  # not under rules/
        "python-coding/references/python-typing.md",  # a hand-written reference (prU D5)
        "python-coding/rules/deep/python-typing.md",  # not one level deep
        "other-skill/rules/python-typing.md",  # another skill's directory
        "python-coding/rules/python-idioms.md",  # not a member's name
    ],
)
def test_skill_write_provenance_keeps_skill_provenance_off_a_members_path(
    tmp_path: Path, rel: str
) -> None:
    path = tmp_path / rel

    [(paths, origin)] = _skill_write_provenance(
        [path], sample_member_skill("python-coding", _TYPING), "claude_code"
    )

    assert paths == [path]
    assert origin.kind == "skill"


def test_dispatch_records_member_references_with_rule_provenance(tmp_path: Path) -> None:
    skill = sample_member_skill("python-coding", _TYPING)

    recorder = dispatch_to_adapters(
        {"shared_skills": SharedSkillsAdapter()}, [], [], [skill], tmp_path
    )

    by_name = {path.name: origin for path, origin in recorder.provenance.items()}
    assert by_name["SKILL.md"].kind == "skill"
    assert by_name["python-typing.md"] == Provenance(
        kind="rule", artifact_id="python-typing", source="acme_overlay", adapter="shared_skills"
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_build_lockfile_gives_output_linked_out_of_the_repo_no_entry(tmp_path: Path) -> None:
    # Regression: the entry kept the resolved absolute path, machine-specific
    # in a committed lockfile; such output is never owned (SPEC §4.2 step 9).
    repo, outside = tmp_path / "repo", tmp_path / "shared"
    (repo / ".claude").mkdir(parents=True)
    outside.mkdir()
    (repo / ".claude" / "skills").symlink_to(outside, target_is_directory=True)
    linked = repo / ".claude" / "skills" / "SKILL.md"
    inside = repo / "AGENTS.md"
    for path in (linked, inside):
        path.write_text("x\n", encoding="utf-8")
    skill = Provenance(kind="skill", artifact_id="demo")

    lockfile = build_lockfile(
        [linked, inside],
        repo,
        "0.2.0",
        provenance={linked.resolve(): skill, inside.resolve(): Provenance(kind="composite")},
    )

    assert [entry.path for entry in lockfile.entries] == ["AGENTS.md"]


@pytest.mark.skipif(os.name != "posix", reason="exec bits are POSIX-only")
def test_build_lockfile_records_the_exec_bit_of_copied_hook_scripts(tmp_path: Path) -> None:
    script = tmp_path / "run.sh"
    script.write_bytes(b"#!/bin/sh\n")
    script.chmod(0o755)
    data = tmp_path / "data.txt"
    data.write_bytes(b"d\n")
    skill_script = tmp_path / "skill.sh"
    skill_script.write_bytes(b"#!/bin/sh\n")
    skill_script.chmod(0o755)
    hook = Provenance(kind="hook", artifact_id="guard-x", source="<repo-local>")

    lockfile = build_lockfile(
        [script, data, skill_script],
        tmp_path,
        "0.2.0",
        provenance={
            script.resolve(): hook,
            data.resolve(): hook,
            skill_script.resolve(): Provenance(kind="skill", artifact_id="s"),
        },
    )

    by_path = {entry.path: entry for entry in lockfile.entries}
    assert by_path["run.sh"].executable is True
    assert by_path["run.sh"].sha256 == compute_hash(b"#!/bin/sh\n")
    assert by_path["data.txt"].executable is False
    assert by_path["skill.sh"].executable is False  # only copied hook scripts (§B.6)


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_build_lockfile_gives_a_looping_written_path_no_entry(tmp_path: Path) -> None:
    """Regression (Python 3.12, where ``Path.resolve()`` raises on a symlink loop): a
    written path whose real path loops raised ``RuntimeError``; it is unreadable, so
    it gets no entry, like any other unreadable path."""
    (tmp_path / "AGENTS.md").write_text("x\n", encoding="utf-8")
    (tmp_path / "self.md").symlink_to("self.md")

    lockfile = build_lockfile(
        [tmp_path / "AGENTS.md", tmp_path / "self.md", tmp_path / "self.md" / "x.md"],
        tmp_path,
        "0.2.0",
        provenance={},
    )

    assert [entry.path for entry in lockfile.entries] == ["AGENTS.md"]


def _whole_file_entries_before_batch(
    written: Sequence[Path], repo_root: Path, provenance: Mapping[Path, Provenance]
) -> list[LockEntry]:
    """``build_lockfile``'s whole-file entries as of 8eb43dff (``Path.resolve()`` per path)."""
    entries: list[LockEntry] = []
    for path in sorted({p.resolve() for p in written}):
        try:
            rel = path.relative_to(repo_root.resolve()).as_posix()
            content = path.read_bytes()
        except (ValueError, OSError):
            continue
        origin = provenance.get(path)
        if origin is None:
            entries.append(LockEntry(path=rel, sha256=compute_hash(content), bytes=len(content)))
            continue
        entry = LockEntry.from_provenance(rel, content, origin)
        if origin.kind == "hook" and os.name == "posix" and path.stat().st_mode & 0o111:
            entry = dataclasses.replace(entry, executable=True)
        entries.append(entry)
    return entries


def _loops(path: Path) -> bool:
    """Whether ``path``'s real path loops: Python 3.12's ``Path.resolve()`` raises there."""
    try:
        os.stat(os.path.realpath(path))
    except OSError as exc:
        return exc.errno == errno.ELOOP
    return False


def _alternating_provenance(written: Sequence[Path]) -> dict[Path, Provenance]:
    """Every other path tagged, alternating hook and skill provenance; keyed resolved, first wins."""
    kinds: tuple[ProvenanceKind, ...] = ("hook", "skill")
    provenance: dict[Path, Provenance] = {}
    for index, path in enumerate(written[::2]):
        origin = Provenance(kind=kinds[index % 2], artifact_id=f"a{index}")
        provenance.setdefault(Path(os.path.realpath(path)), origin)
    return provenance


def _entries_now(
    written: Sequence[Path], root: Path, provenance: Mapping[Path, Provenance]
) -> list[LockEntry]:
    return build_lockfile(written, root, "0.2.0", provenance=provenance).entries


def _entries_or_error(
    stamp: Callable[[Sequence[Path], Path, Mapping[Path, Provenance]], list[LockEntry]],
    written: Sequence[Path],
    root: Path,
    provenance: Mapping[Path, Provenance],
) -> object:
    """``stamp(...)``, or the type and message it raises (a looping root on Python 3.12)."""
    try:
        return stamp(written, root, provenance)
    except Exception as exc:  # the parity check compares any exception
        return (type(exc), str(exc))


def _assert_entries_match_before_batch(written: list[Path], roots: Sequence[Path]) -> None:
    """The very entries (or exception) of the old implementation, for every root."""
    provenance = _alternating_provenance(written)
    for root in roots:
        expected = _entries_or_error(_whole_file_entries_before_batch, written, root, provenance)
        assert _entries_or_error(_entries_now, written, root, provenance) == expected, root


def _zoo_written(tmp_path: Path) -> list[Path]:
    """Every link-zoo spelling, plus an executable hook script, as written paths."""
    build_link_zoo(tmp_path)
    hook = tmp_path / "d1" / "hook.sh"
    hook.write_bytes(b"#!/bin/sh\n")
    hook.chmod(0o755)
    return [hook, *link_zoo_queries(tmp_path)]


_ZOO_ROOTS = ("", "d1", "dir_link", "chain1")


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_build_lockfile_matches_the_per_path_implementation_over_every_link_shape(
    tmp_path: Path,
) -> None:
    written = [path for path in _zoo_written(tmp_path) if not _loops(path)]

    _assert_entries_match_before_batch(written, [tmp_path / root for root in _ZOO_ROOTS])

    lockfile = build_lockfile(
        written, tmp_path, "0.2.0", provenance=_alternating_provenance(written)
    )
    assert [entry.path for entry in lockfile.entries if entry.executable] == ["d1/hook.sh"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
@pytest.mark.parametrize("seed", range(3))
def test_build_lockfile_matches_the_per_path_implementation_on_random_trees(
    tmp_path: Path, seed: int
) -> None:
    rng = random.Random(seed)
    nodes = random_link_tree(tmp_path, rng)
    written = [path for path in random_tree_queries(nodes, rng) if not _loops(path)]
    _assert_entries_match_before_batch(written, [tmp_path, *rng.sample(nodes, 1)])


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_build_lockfile_leaves_out_every_looping_link_shape(tmp_path: Path) -> None:
    """Regression (Python 3.12, where ``Path.resolve()`` raises on a symlink loop): the
    looping written paths are left out, as on 3.13, the rest stamped as before."""
    written = _zoo_written(tmp_path)
    loop_free = [path for path in written if not _loops(path)]
    provenance = _alternating_provenance(written)
    assert len(loop_free) < len(written)
    for root in (tmp_path / root for root in _ZOO_ROOTS):
        expected = _whole_file_entries_before_batch(loop_free, root, provenance)
        assert build_lockfile(written, root, "0.2.0", provenance=provenance).entries == expected


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_build_lockfile_resolves_a_looping_root_only_when_a_path_was_written(
    tmp_path: Path,
) -> None:
    """Pins the root guard: as of 8eb43dff the root was resolved once per written path, so
    on Python 3.12 (where ``Path.resolve()`` raises on a symlink loop) a looping root
    raised only when something was written; with nothing written the scoped entries
    are stamped alone."""
    root = tmp_path / "loop"
    root.symlink_to("loop")
    (tmp_path / "AGENTS.md").write_text("x\n", encoding="utf-8")

    lockfile = build_lockfile([], root, "0.2.0", provenance={}, managed=[_SCOPED])

    assert lockfile.entries == [_SCOPED]
    for written in ([], [tmp_path / "AGENTS.md"]):
        expected = _entries_or_error(_whole_file_entries_before_batch, written, root, {})
        assert _entries_or_error(_entries_now, written, root, {}) == expected, written


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_real_written_paths_resolves_afresh_on_every_call(tmp_path: Path) -> None:
    """Pins the batch's scope, one per call and never module-level: ``_run_sync`` and
    ``build_lockfile`` each call it, with deletes between, so a directory relinked
    between two calls is seen by the second, as with per-path ``Path.resolve()``."""
    written = relinkable_outputs(tmp_path)
    first = real_written_paths(written)
    relink_directory(tmp_path / "out", tmp_path / "other")

    second = real_written_paths(written)

    assert second == {path.resolve() for path in written}
    assert second != first


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_real_written_paths_equals_resolving_each_loop_free_path(tmp_path: Path) -> None:
    """Characterization of ``real_written_paths`` (also ``_run_sync``'s ``resolved_written``):
    the set ``{p.resolve() for p in written}`` the old code built, on every loop-free shape."""
    written = [path for path in _zoo_written(tmp_path) if not _loops(path)]

    assert real_written_paths(written) == {path.resolve() for path in written}


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_real_written_paths_leaves_a_loop_unresolved_instead_of_raising(tmp_path: Path) -> None:
    """Regression (Python 3.12, where ``Path.resolve()`` raises on a symlink loop)."""
    (tmp_path / "self.md").symlink_to("self.md")
    looping = [tmp_path / "self.md", tmp_path / "self.md" / "x.md"]

    assert real_written_paths(looping) == {Path(os.path.realpath(path)) for path in looping}
