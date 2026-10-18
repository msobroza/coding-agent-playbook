"""Tests for the secret-path catalog (specs/prK-lifecycle-hooks.md §P7, SPEC §17.3).

``security.patterns`` is the single home of ``SECRET_PATH_GLOBS`` and
``SECRET_PATH_EXEMPT``. The match/no-match tables pin the catalog through the
one predicate that reads it, ``security.paths.is_secret_path``, with the home
directory and the platform injected so the tables are hermetic.
"""

from __future__ import annotations

import sys

import pytest

from coding_agent_playbook.security.paths import is_secret_path
from coding_agent_playbook.security.patterns import (
    EXAMPLE_SECRET_ALLOWLIST,
    SECRET_CONTENT_RULES,
    SECRET_GLOB_EXEMPT,
    SECRET_PATH_EXEMPT,
    SECRET_PATH_GLOBS,
    SECRET_SCAN_SKIP_NAMES,
)
from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after

_HOME = "/home/dev"

#: SPEC §17.3's original four globs; the catalog must keep every one of them.
_SPEC_17_3_GLOBS = (".env*", "*.pem", "*.key", "*credentials*")

_SECRET = [
    # .env* (dotenv files, any directory)
    ".env",
    "deploy/.env",
    ".env.local",
    ".env.production",
    ".envrc",
    # key material and stores
    "certs/server.pem",
    "tls/private.key",
    "keys/client.p12",
    "client.pfx",
    "truststore.jks",
    "android/release.keystore",
    "id_rsa",
    "deploy/id_rsa_github",
    "id_ed25519",
    "id_ecdsa",
    "id_ecdsa_sk",
    "id_dsa",
    # *credentials* outside source code (notebooks keep their cell outputs)
    "credentials",
    "credentials.json",
    "config/gcp-credentials.json",
    "aws_credentials.yaml",
    "notebooks/credentials.ipynb",
    ".git-credentials",
    # tool credential files
    ".netrc",
    ".pypirc",
    ".npmrc",
    "pip.conf",
    "uv.toml",
    ".vault-token",
    "krb5cc_1000",
    # infrastructure state and password vaults
    "infra/terraform.tfstate",
    "infra/terraform.tfstate.backup",
    "prod.tfvars",
    "prod.tfvars.json",
    # the code-suffix exemption spares *credentials* only, never another glob
    ".env.credentials.py",
    "id_rsa_credentials.sh",
    "team.kdbx",
    # the per-user credential directories and files under ~/
    f"{_HOME}/.aws/credentials",
    f"{_HOME}/.aws/config",
    f"{_HOME}/.ssh/config",
    f"{_HOME}/.ssh/known_hosts",
    f"{_HOME}/.kube/config",
    f"{_HOME}/.config/gcloud/application_default_credentials.json",
    f"{_HOME}/.config/gcloud/configurations/config_default",
    f"{_HOME}/.config/gh/hosts.yml",
    f"{_HOME}/.docker/config.json",
    f"{_HOME}/.m2/settings.xml",
    f"{_HOME}/.claude/.credentials.json",
    "~/.aws/config",
]

_NOT_SECRET = [
    # documented .env templates
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    "config/.env.example",
    # source code that merely handles credentials
    "credentials.py",
    "src/app/credentials.py",
    "web/src/credentials.ts",
    "internal/credentials.go",
    "scripts/rotate_credentials.sh",
    # public keys
    "id_rsa.pub",
    "deploy/id_ed25519_ci.pub",
    "id_ecdsa.pub",
    "id_dsa.pub",
    f"{_HOME}/.ssh/id_rsa.pub",
    # look-alikes
    "README.md",
    "pyproject.toml",
    "src/env.py",
    "environment.yml",
    "keys.py",
    "server.pem.md",
    # home-anchored globs need the real home prefix, not a look-alike
    ".ssh/config",
    "/srv/other/.aws/config",
    f"{_HOME}il/.aws/config",
    f"{_HOME}/.awsome/config",
    f"{_HOME}/.kube/cache/discovery.json",
    f"{_HOME}/.docker/daemon.json",
    f"{_HOME}/.config/gh/config.yml",
    f"{_HOME}/project/src/main.py",
]


@pytest.mark.parametrize("path", _SECRET)
def test_secret_paths_match(path: str) -> None:
    assert is_secret_path(path, home=_HOME, platform="linux") is True


@pytest.mark.parametrize("path", _NOT_SECRET)
def test_non_secret_paths_do_not_match(path: str) -> None:
    assert is_secret_path(path, home=_HOME, platform="linux") is False


@pytest.mark.parametrize("platform", ["darwin", "win32"])
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".ENV", True),
        ("CREDENTIALS.json", True),
        ("Server.PEM", True),
        (".Env.Example", False),
        ("Credentials.PY", False),
        ("ID_RSA.PUB", False),
    ],
)
def test_case_insensitive_platforms_fold_case(path: str, expected: bool, platform: str) -> None:
    assert is_secret_path(path, home=_HOME, platform=platform) is expected


@pytest.mark.parametrize("path", [".ENV", "CREDENTIALS.json", "Server.PEM"])
def test_case_sensitive_platform_does_not_fold_case(path: str) -> None:
    assert is_secret_path(path, home=_HOME, platform="linux") is False


def test_darwin_folds_the_home_prefix() -> None:
    assert is_secret_path("/users/dev/.AWS/config", home="/Users/Dev", platform="darwin") is True


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("C:\\Users\\Dev\\.AWS\\credentials", True),
        ("C:\\Users\\dev\\.kube\\config", True),
        ("C:\\proj\\.env", True),
        ("C:\\proj\\.env.example", False),
        ("C:\\proj\\src\\credentials.py", False),
    ],
)
def test_win32_backslash_paths(path: str, expected: bool) -> None:
    assert is_secret_path(path, home="C:\\Users\\dev", platform="win32") is expected


def test_catalog_keeps_every_spec_17_3_glob() -> None:
    assert set(_SPEC_17_3_GLOBS) <= set(SECRET_PATH_GLOBS)


def test_catalog_entries_are_unique_tuples() -> None:
    assert isinstance(SECRET_PATH_GLOBS, tuple)
    assert isinstance(SECRET_PATH_EXEMPT, tuple)
    assert len(set(SECRET_PATH_GLOBS)) == len(SECRET_PATH_GLOBS)
    assert len(set(SECRET_PATH_EXEMPT)) == len(SECRET_PATH_EXEMPT)


@pytest.mark.parametrize("glob", SECRET_PATH_GLOBS)
def test_glob_grammar_is_basename_or_home_anchored(glob: str) -> None:
    # is_secret_path understands exactly two glob shapes (security/patterns.py).
    is_home_anchored = glob.startswith("~/") and "~" not in glob[2:]
    assert is_home_anchored or ("/" not in glob and "~" not in glob), glob


@pytest.mark.parametrize(
    "glob", [*SECRET_PATH_EXEMPT, *(g for scoped in SECRET_GLOB_EXEMPT.values() for g in scoped)]
)
def test_exemptions_are_basename_globs(glob: str) -> None:
    assert "/" not in glob and "~" not in glob, glob


def test_scoped_exemptions_name_catalog_globs() -> None:
    """A scoped exemption only cancels its own glob, so that glob must exist."""
    assert set(SECRET_GLOB_EXEMPT) <= set(SECRET_PATH_GLOBS)
    assert "*credentials*.py" in SECRET_GLOB_EXEMPT["*credentials*"]
    assert not any("credentials" in glob for glob in SECRET_PATH_EXEMPT)


def test_patterns_module_imports_nothing_at_runtime() -> None:
    loaded = new_modules_after("import coding_agent_playbook.security.patterns")
    assert loaded == ["coding_agent_playbook.security", "coding_agent_playbook.security.patterns"]


def test_paths_module_imports_only_the_stdlib() -> None:
    loaded = new_modules_after("import coding_agent_playbook.security.paths")
    foreign = [
        name
        for name in loaded
        if not name.startswith(engine_module("coding_agent_playbook.security"))
        and name.split(".")[0] not in sys.stdlib_module_names
    ]
    assert foreign == []


def test_secret_content_rule_ids_unique_and_compile() -> None:
    import re

    from coding_agent_playbook.security.secrets import screen_regex

    ids = [rule_id for rule_id, _, _ in SECRET_CONTENT_RULES]
    assert len(set(ids)) == len(ids)
    for rule_id, source, label in SECRET_CONTENT_RULES:
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", rule_id), rule_id
        assert label and re.compile(source).groups == 0, rule_id
        assert screen_regex(source) is None, rule_id  # the engine passes its own screen


def test_example_allowlist_and_skip_names_are_frozen() -> None:
    assert "AKIAIOSFODNN7EXAMPLE" in EXAMPLE_SECRET_ALLOWLIST
    assert {"uv.lock", "poetry.lock", "package-lock.json"} <= SECRET_SCAN_SKIP_NAMES
    assert isinstance(EXAMPLE_SECRET_ALLOWLIST, frozenset)
    assert isinstance(SECRET_SCAN_SKIP_NAMES, frozenset)
