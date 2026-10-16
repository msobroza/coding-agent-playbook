"""Hosts read from command words as strings only (specs/prK-hook-pack.md §E.4).

``extract_hosts`` / ``is_loopback`` are pure: remotes are resolved by the
caller (``git remote -v``), and no function may resolve a name, since a DNS
lookup is itself egress. The ``getaddrinfo`` spy proves it.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime._hosts import (
    extract_hosts,
    host_matches,
    is_loopback,
    scp_host,
    url_host,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        (["curl", "https://Example.COM:8443/x?q=1"], ["example.com"]),
        (["scp", "a.tar", "deploy@build-01.corp:/tmp"], ["build-01.corp"]),
        (["scp", "a.tar", "host:/tmp"], ["host"]),
        (["pip", "install", "git+https://github.com/org/pkg.git#egg=pkg"], ["github.com"]),
        (
            ["pip", "install", "pkg @ https://files.example/pkg-1.0-py3-none-any.whl"],
            ["files.example"],
        ),
        (["pip", "install", "--index-url=https://pypi.corp/simple", "x"], ["pypi.corp"]),
        (
            ["uv", "add", "--extra-index-url", "https://download.pytorch.org/whl/cu121"],
            ["download.pytorch.org"],
        ),
        (["git", "push", "origin", "feat"], ["gitlab.example"]),
        (["git", "push", "https://[::1]:9000/r.git"], ["::1"]),
        (["rm", "-rf", "./a:b", "C:/x", "-o", "x"], []),
        (["echo", "a:b c"], []),
    ],
)
def test_extract_hosts(words: list[str], expected: list[str]) -> None:
    remotes = {"origin": "git@gitlab.example:team/repo.git"}

    assert extract_hosts(words, remotes=remotes) == expected


def test_url_host_bare_form_only_on_request() -> None:
    assert url_host("x.io/upload") is None
    assert url_host("x.io/upload", bare=True) == "x.io"
    assert url_host("localhost:8000/x", bare=True) is None  # no dot: not a bare host
    assert scp_host("--opt=a:b") is None


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.8.9.10", True),
        ("::1", True),
        ("[::1]", True),
        ("::ffff:127.0.0.1", True),
        ("localhost", True),
        ("LOCALHOST.", True),
        ("10.0.0.5", False),
        ("192.168.1.10", False),
        ("172.16.0.1", False),
        ("evil.localhost.example", False),
        ("0.0.0.0", False),
        ("999.1.1.1", False),
        ("example.com", False),
    ],
)
def test_is_loopback(host: str, expected: bool) -> None:
    assert is_loopback(host) is expected


@pytest.mark.parametrize(
    ("host", "suffixes", "expected"),
    [
        ("example.com", ["example.com"], True),
        ("api.example.com", ["example.com"], True),
        ("api.example.com", ["*.example.com"], True),
        ("api.example.com", [".example.com"], True),
        ("badexample.com", ["example.com"], False),
        ("example.com.evil.io", ["example.com"], False),
        ("Example.COM.", ["EXAMPLE.com"], True),
        ("x.io", [], False),
        ("x.io", [""], False),
    ],
)
def test_suffix_match(host: str, suffixes: list[str], expected: bool) -> None:
    assert host_matches(host, suffixes) is expected


@pytest.fixture
def no_dns(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    """A ``socket.getaddrinfo`` / ``gethostbyname`` spy that records every lookup."""
    calls: list[Any] = []

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        raise AssertionError("a guard resolved a host name")

    monkeypatch.setattr(socket, "getaddrinfo", spy)
    monkeypatch.setattr(socket, "gethostbyname", spy)
    yield calls


def test_never_resolves_dns(no_dns: list[Any]) -> None:
    words = ["curl", "-T", "dump.sql", "https://x.io", "deploy@host:/srv", "evil.example"]

    hosts = extract_hosts(words)
    loopbacks = [is_loopback(host) for host in [*hosts, "localhost", "127.0.0.1", "::1"]]

    assert hosts == ["x.io", "host"]
    assert loopbacks == [False, False, True, True, True]
    assert no_dns == []
