"""The secret-content library (``security/secrets.py``, specs/prK-hook-pack.md §E.4).

One scanner for secret-content-guard, stop-diff-sweep and ``playbook
scan-secrets``. Every sample token is assembled at run time (``_tok``), so this
file never holds a real-shaped token for a push-protection scanner, or the
engine's own ``playbook-secrets`` hook, to trip on.
"""

from __future__ import annotations

import dataclasses
import json
import sys

import pytest

from coding_agent_playbook.security.secrets import (
    MAX_REGEX_CHARS,
    AddedText,
    SecretFinding,
    allow_secret_rules,
    scan_added_lines,
    scan_bounded,
    scan_text,
    screen_regex,
)
from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after


def _tok(*parts: str) -> str:
    return "".join(parts)


AWS_KEY = _tok("AKIA", "Z7Q2" * 4)
GITHUB_TOKEN = _tok("gh", "p_", "a1B2" * 9)

# GitLab token bodies (GitLab "token overview" and its token generators): a Devise
# friendly token (20 chars of [0-9A-Za-z_-]) and a routable body (27-300 base64url
# chars, ``.``, an optional 2-char version and ``.``, then 2 length + 7 CRC chars).
_FRIENDLY20 = "A1b2-C3d4_" * 2
_ROUTABLE = _tok("Ab1-Cd2_" * 4, ".01.", "0w", "1b2c3d4")
_UNVERSIONED = _tok("Ab1-Cd2_" * 4, ".", "0w", "1b2c3d4")
_SHORT_ROUTABLE = _tok("Ab1-Cd2_" * 3, "Ab", ".01.", "0w", "1b2c3d4")  # a 26-char payload
_JWT_BODY = _tok("ey", "JhbGciOiJSUzI1NiJ9.", "ey", "JzdWIiOiIxMjMifQ.", "c2lnbmF0dXJlMTIz")
GITLAB_TOKEN = _tok("gl", "pat-", _FRIENDLY20)

#: rule id -> (a line it must flag, a near miss it must pass)
_RULE_CASES: dict[str, tuple[str, str]] = {
    "private-key": (_tok("-----BEGIN ", "RSA PRIVATE KEY-----"), "-----BEGIN PUBLIC KEY-----"),
    "aws-access-key-id": (
        f"key = '{AWS_KEY}'",
        _tok("key = 'XAKIA", "Z7Q2" * 4, "'"),
    ),
    "github-token": (f"token={GITHUB_TOKEN}", _tok("token=gh", "x_", "a1B2" * 9)),
    "gitlab-token": (f"GITLAB_TOKEN={GITLAB_TOKEN}", _tok("GITLAB_TOKEN=gl", "pax-", _FRIENDLY20)),
    "gitlab-runner-registration-token": (
        _tok("--registration-token GR", "1348941", _FRIENDLY20),
        _tok("--registration-token GR", "1348942", _FRIENDLY20),
    ),
    "slack-token": (
        _tok("SLACK=xo", "xb-", "1234567890-abcdefghij"),
        _tok("SLACK=xo", "xq-", "1234567890-abcdefghij"),
    ),
    "google-api-key": (
        _tok("k = AI", "za", "Sy", "B" * 33),
        _tok("k = AI", "za", "B" * 34, " end"),
    ),
    "stripe-live-key": (
        _tok("STRIPE=sk", "_live_", "4eC39HqLyjWDarjtT1zdp7dc"),
        _tok("STRIPE=sk", "_test_", "4eC39HqLyjWDarjtT1zdp7dc"),
    ),
    "anthropic-api-key": (
        _tok("ANTHROPIC_API_KEY=sk-", "ant-", "api03-", "A1" * 15),
        _tok("ANTHROPIC_API_KEY=sk-", "ant-", "short"),
    ),
    "openai-api-key": (
        _tok("OPENAI_API_KEY=sk-", "proj-", "B2" * 15),
        _tok("OPENAI_API_KEY=sk-", "projx-", "B2" * 15),
    ),
    "azure-storage-key": (
        _tok("DefaultEndpointsProtocol=https;Account", "Key=", "Ab1+" * 22, "=="),
        _tok("DefaultEndpointsProtocol=https;Account", "Key=", "short"),
    ),
    "jwt": (
        _tok("Bearer ey", "JhbGciOiJIUzI1NiJ9.", "ey", "JzdWIiOiIxMjMifQ.", "c2lnbmF0dXJlMTIz"),
        "Bearer eyJhbGciOiJIUzI1NiJ9",
    ),
    "url-credentials": (
        _tok("remote = https://deploy:", "s3cr3tP4ss", "@git.example.com/r.git"),
        "remote = https://user:${TOKEN}@git.example.com/r.git",
    ),
}


@pytest.mark.parametrize("rule_id", sorted(_RULE_CASES))
def test_rule_table(rule_id: str) -> None:
    hit, miss = _RULE_CASES[rule_id]

    assert [f.rule_id for f in scan_text(f"x = 1\n{hit}\n", "src/app.py")] == [rule_id]
    assert scan_text(miss, "src/app.py") == []


def _gitlab_sample(prefix: str, body: str) -> str:
    """A GitLab-shaped sample, assembled so this file never spells one out."""
    return _tok("gl", prefix, body)


#: Each GitLab prefix at every documented length (hits), and a near miss of each.
_GITLAB_HITS = [
    pytest.param(GITLAB_TOKEN, id="glpat_legacy_20"),
    pytest.param(_gitlab_sample("pat-", _ROUTABLE), id="glpat_routable"),
    pytest.param(_gitlab_sample("pat-", _UNVERSIONED), id="glpat_routable_unversioned"),
    pytest.param(_gitlab_sample("oas-", "0f1e" * 16), id="gloas_64_hex"),
    pytest.param(_gitlab_sample("dt-", _FRIENDLY20), id="gldt_20"),
    pytest.param(_gitlab_sample("rt-", _FRIENDLY20), id="glrt_20"),
    pytest.param(_gitlab_sample("rt-", _tok("t3_", _FRIENDLY20)), id="glrt_partitioned"),
    pytest.param(_gitlab_sample("rt-", _ROUTABLE), id="glrt_routable"),
    pytest.param(_gitlab_sample("rtr-", _FRIENDLY20), id="glrtr_20"),
    pytest.param(_gitlab_sample("rtr-", _ROUTABLE), id="glrtr_routable"),
    pytest.param(_gitlab_sample("ptt-", _FRIENDLY20), id="glptt_20"),
    pytest.param(_gitlab_sample("ptt-", "0f1e" * 10), id="glptt_40_hex"),
    pytest.param(_gitlab_sample("ft-", _FRIENDLY20), id="glft_20"),
    pytest.param(_gitlab_sample("ft-", _tok("0f1e" * 16, "-", "42")), id="glft_path_dependent"),
    pytest.param(_gitlab_sample("cbt-", _tok("6a", "_", _FRIENDLY20)), id="glcbt_legacy"),
    pytest.param(_gitlab_sample("cbt-", _JWT_BODY), id="glcbt_jwt"),
    # GitLab's source makes these two JWT tokens; its token overview does not list them
    pytest.param(_gitlab_sample("sat-", _JWT_BODY), id="glsat_jwt"),
    pytest.param(_gitlab_sample("iamat-", _JWT_BODY), id="gliamat_jwt"),
    pytest.param(_gitlab_sample("soat-", _FRIENDLY20), id="glsoat_20"),
    pytest.param(_gitlab_sample("imt-", "z9y8x" * 5), id="glimt_25"),
    pytest.param(_gitlab_sample("imt-", "z9y8x" * 4 + "w"), id="glimt_unpadded_21"),
    pytest.param(_gitlab_sample("agent-", "Ab1-Cd2_e" * 5 + "F3g4h"), id="glagent_50"),
    pytest.param(_gitlab_sample("agent-", _ROUTABLE), id="glagent_routable"),
    pytest.param(_gitlab_sample("ffct-", _FRIENDLY20), id="glffct_20"),
    pytest.param(_gitlab_sample("wt-", _ROUTABLE), id="glwt_routable"),
]

_GITLAB_MISSES = [
    pytest.param(_gitlab_sample("pat-", _FRIENDLY20[:19]), id="glpat_19"),
    pytest.param(_gitlab_sample("pat-", _tok(_FRIENDLY20, "x")), id="glpat_21"),
    pytest.param(_gitlab_sample("pat-", _SHORT_ROUTABLE), id="glpat_routable_26"),
    pytest.param(_tok("x", _gitlab_sample("pat-", _FRIENDLY20)), id="glpat_inside_a_word"),
    pytest.param(_gitlab_sample("oas-", "0f1e" * 15 + "0f1"), id="gloas_63_hex"),
    pytest.param(_gitlab_sample("dt-", _FRIENDLY20[:19]), id="gldt_19"),
    pytest.param(_gitlab_sample("rt-", _tok("t4_", _FRIENDLY20)), id="glrt_unknown_partition"),
    pytest.param(_gitlab_sample("rtx-", _FRIENDLY20), id="glrtx"),
    pytest.param(_gitlab_sample("rtr-", _FRIENDLY20[:19]), id="glrtr_19"),
    pytest.param(_gitlab_sample("ptt-", "0f1e" * 9 + "0f1"), id="glptt_39_hex"),
    pytest.param(_gitlab_sample("ft-", _tok(_FRIENDLY20, "x")), id="glft_21"),
    pytest.param(
        _gitlab_sample("cbt-", _tok("6a7b8c", "_", _FRIENDLY20)), id="glcbt_6_char_partition"
    ),
    pytest.param(_gitlab_sample("cbt-", "eyJhbGciOiJSUzI1NiJ9"), id="glcbt_jwt_header_only"),
    pytest.param(_gitlab_sample("sat-", "eyJhbGciOiJSUzI1NiJ9"), id="glsat_jwt_header_only"),
    pytest.param(_gitlab_sample("sat-", _FRIENDLY20), id="glsat_20_no_jwt"),
    pytest.param(_gitlab_sample("iamat-", _FRIENDLY20), id="gliamat_20_no_jwt"),
    pytest.param(_gitlab_sample("iamat_", _JWT_BODY), id="gliamat_underscore"),
    pytest.param(_gitlab_sample("soat-", _FRIENDLY20[:19]), id="glsoat_19"),
    pytest.param(_gitlab_sample("imt-", "z9y8x" * 5 + "w"), id="glimt_26"),
    pytest.param(_gitlab_sample("agent-", "Ab1-Cd2_e" * 5 + "F3g4"), id="glagent_49"),
    pytest.param(_gitlab_sample("ffct-", _FRIENDLY20[:19]), id="glffct_19"),
    pytest.param(_gitlab_sample("wt-", _FRIENDLY20), id="glwt_20"),
    pytest.param(_tok("GR", "1348941", _FRIENDLY20[:19]), id="GR1348941_19"),
    pytest.param(_tok("xGR", "1348941", _FRIENDLY20), id="GR1348941_inside_a_word"),
]


@pytest.mark.parametrize("token", _GITLAB_HITS)
def test_gitlab_token_rule_matches_every_documented_prefix_and_length(token: str) -> None:
    findings = scan_text(f'token: "{token}"\n', "ci/vars.yml")

    assert [(f.rule_id, f.length) for f in findings] == [("gitlab-token", len(token))]


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(GITLAB_TOKEN, id="glpat"),
        pytest.param(_gitlab_sample("sat-", _JWT_BODY), id="glsat_jwt"),
    ],
)
def test_gitlab_token_rule_matches_after_an_instance_prefix(token: str) -> None:
    """An admin's instance prefix (``<prefix>-glpat-...``) leaves the GitLab prefix in place."""
    findings = scan_text(f"PRIVATE-TOKEN: acme-{token}\n", "notes.md")

    assert [(f.rule_id, f.length) for f in findings] == [("gitlab-token", len(token))]


@pytest.mark.parametrize("text", _GITLAB_MISSES)
def test_gitlab_rules_pass_near_misses(text: str) -> None:
    assert scan_text(f'token: "{text}"\n', "ci/vars.yml") == []


def test_finding_reports_rule_line_and_length() -> None:
    (finding,) = scan_text(f"a = 1\nb = 2\nkey = '{AWS_KEY}'\n", "src/conf.py")

    assert (finding.path, finding.line, finding.rule_id, finding.length) == (
        "src/conf.py",
        3,
        "aws-access-key-id",
        20,
    )
    assert str(finding) == "src/conf.py:3: aws-access-key-id: AWS access key id (20 chars)"


def test_finding_never_carries_secret_characters() -> None:
    findings = scan_text(f"{AWS_KEY}\n{GITHUB_TOKEN}\n", "deploy/vars.sh")

    assert len(findings) == 2
    assert "text" not in {field.name for field in dataclasses.fields(SecretFinding)}
    for finding in findings:
        for rendered in (repr(finding), str(finding), json.dumps(finding.to_json())):
            assert AWS_KEY[4:] not in rendered
            assert GITHUB_TOKEN[4:] not in rendered


def test_documented_example_keys_are_allowlisted() -> None:
    text = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"

    assert scan_text(text, "docs/setup.md") == []


def test_low_entropy_password_assignment_passes() -> None:
    text = 'password = "hunter2"\nDB_PASSWORD=changeme\nurl = "postgres://u:password@db/x"\n'

    assert scan_text(text, "settings.py") == []


def test_notebook_scans_sources_and_text_outputs_only() -> None:
    image_with_key_shape = _tok("iVBORw0KGgo", "AI", "za", "Sy", "B" * 33, "AAAA")
    notebook = {
        "cells": [
            {"cell_type": "code", "source": [f"key = '{AWS_KEY}'\n"], "outputs": []},
            {
                "cell_type": "code",
                "source": "print(token)",
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": [GITHUB_TOKEN]},
                    {
                        "output_type": "display_data",
                        "data": {"image/png": image_with_key_shape, "text/plain": "<Figure>"},
                    },
                ],
            },
        ]
    }

    findings = scan_text(json.dumps(notebook), "nb/explore.ipynb")

    assert sorted(f.rule_id for f in findings) == ["aws-access-key-id", "github-token"]
    assert {f.line for f in findings} == {0}  # a notebook finding names the file, not a line
    assert str(findings[0]).startswith("nb/explore.ipynb: ")


def test_malformed_notebook_is_scanned_as_text() -> None:
    assert [f.rule_id for f in scan_text(f"{{ broken {AWS_KEY}", "nb/x.ipynb")] == [
        "aws-access-key-id"
    ]


def test_oversized_text_scans_head_and_tail_and_marks_partial() -> None:
    filler = "x = 1\n" * 900_000  # ~5.4 MB
    text = f"a = 0\nk1 = '{AWS_KEY}'\n{filler}k2 = '{GITHUB_TOKEN}'\n{filler}k3 = '{AWS_KEY}'\n"

    scan = scan_bounded(text, "big.py")

    assert scan.partial is True
    assert [(f.rule_id, f.line) for f in scan.findings] == [
        ("aws-access-key-id", 2),
        ("aws-access-key-id", text.count("\n")),
    ]


def test_small_text_is_scanned_whole() -> None:
    scan = scan_bounded(f"x\n{GITHUB_TOKEN}\n", "small.py")

    assert (scan.partial, [f.line for f in scan.findings]) == (False, [2])


def test_lockfiles_and_binaries_skipped() -> None:
    assert scan_text(f"hash = '{AWS_KEY}'", "uv.lock") == []
    assert scan_text(f"x = '{AWS_KEY}'", "web/package-lock.json") == []
    assert scan_text(f"\x00\x01{AWS_KEY}", "model.bin") == []


def test_scan_added_lines_uses_new_line_numbers() -> None:
    lines = [
        AddedText("src/a.py", 10, "x = 1"),
        AddedText("src/a.py", 12, f"key = '{AWS_KEY}'"),
        AddedText("uv.lock", 3, f"h = '{AWS_KEY}'"),
        AddedText("conf/b.env.example", 7, f"T={GITHUB_TOKEN}"),
    ]

    findings = scan_added_lines(lines)

    assert [(f.path, f.line, f.rule_id) for f in findings] == [
        ("src/a.py", 12, "aws-access-key-id"),
        ("conf/b.env.example", 7, "github-token"),
    ]


def test_scan_added_lines_skips_notebook_image_payloads() -> None:
    payload = _tok('      "image/png": "iVBOR', "AI", "za", "Sy", "B" * 33, '"')
    lines = [
        AddedText("nb/a.ipynb", 40, payload),
        AddedText("nb/a.ipynb", 41, f'    "key = {AWS_KEY}\\n",'),
    ]

    assert [f.line for f in scan_added_lines(lines)] == [41]


def test_allow_secret_rules() -> None:
    line = "key = x  # playbook: allow-secret aws-access-key-id, jwt  # test fixture"

    assert allow_secret_rules(line) == frozenset({"aws-access-key-id", "jwt"})
    assert allow_secret_rules("key = x  # playbook: allow-secret") == frozenset()
    assert allow_secret_rules("key = x") == frozenset()


def test_pragma_naming_the_rule_marks_the_finding() -> None:
    text = (
        f"a = '{AWS_KEY}'  # playbook: allow-secret aws-access-key-id\n"
        f"b = '{AWS_KEY}'  # playbook: allow-secret jwt\n"
    )

    assert [f.pragma for f in scan_text(text, "fixtures.py")] == [True, False]


def test_screen_regex_rejects_nested_quantifiers() -> None:
    for pattern in ("(a+)+$", "(a*)*b", "(?:x|y+)*z", "((ab)+c)+"):
        problem = screen_regex(pattern)
        assert problem is not None and "nests unbounded" in problem and repr(pattern) in problem


def test_screen_regex_rejects_overlong_and_invalid() -> None:
    overlong = screen_regex("a" * (MAX_REGEX_CHARS + 1))
    invalid = screen_regex("(unclosed")

    assert overlong is not None and str(MAX_REGEX_CHARS) in overlong
    assert invalid is not None and "does not compile" in invalid


def test_screen_regex_walks_cpythons_own_parser() -> None:
    from coding_agent_playbook.security import _regex_shape

    # Private but stable on 3.12/3.13; sre_parse would warn (filterwarnings = error).
    assert _regex_shape._PARSER.__name__ == "re._parser"


def test_screen_regex_accepts_convention_rows() -> None:
    for pattern in (r"^uv run (mypy|pytest)\b", r"[a-z]+@[a-z]+\.com", r"(?:ab){2,5}c+"):
        assert screen_regex(pattern) is None, pattern


def test_secrets_module_imports_only_stdlib() -> None:
    loaded = new_modules_after("import coding_agent_playbook.security.secrets")
    foreign = [
        name
        for name in loaded
        if not name.startswith(engine_module("coding_agent_playbook.security"))
        and name.split(".")[0] not in sys.stdlib_module_names
    ]
    assert foreign == []
    assert "json" not in loaded  # the notebook branch imports it on first use
