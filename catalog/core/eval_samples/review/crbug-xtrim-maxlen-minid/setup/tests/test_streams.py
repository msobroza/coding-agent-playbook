from typing import Any

from src.streams import StreamCommands


class FakeRedis:
    """Records each command instead of sending it to a server."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def execute_command(self, *args: Any) -> int:
        self.calls.append(args)
        return 0


def test_xtrim_is_approximate_by_default() -> None:
    redis = FakeRedis()
    StreamCommands(redis.execute_command).xtrim("events", 100)
    assert redis.calls == [("XTRIM", "events", b"MAXLEN", b"~", 100)]


def test_xtrim_can_trim_exactly() -> None:
    redis = FakeRedis()
    StreamCommands(redis.execute_command).xtrim("events", 100, approximate=False)
    assert redis.calls == [("XTRIM", "events", b"MAXLEN", 100)]


def test_xtrim_by_minid() -> None:
    redis = FakeRedis()
    StreamCommands(redis.execute_command).xtrim("events", minid="1700000000000-0")
    assert redis.calls == [("XTRIM", "events", b"MINID", b"~", "1700000000000-0")]


def test_xtrim_with_a_limit() -> None:
    redis = FakeRedis()
    StreamCommands(redis.execute_command).xtrim("events", 100, limit=10)
    assert redis.calls == [("XTRIM", "events", b"MAXLEN", b"~", 100, b"LIMIT", 10)]
