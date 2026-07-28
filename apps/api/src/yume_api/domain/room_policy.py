"""Ordered tool-to-room mapping for the Yume office."""

from collections.abc import Sequence
from fnmatch import fnmatch

from yume_api.contracts.events import RoomId


class RoomPolicy:
    """Resolve Hermes tool names into the most appropriate office room."""

    DEFAULTS: tuple[tuple[str, RoomId], ...] = (
        ("memory*", "memory"),
        ("web_*", "research"),
        ("browser*", "research"),
        ("terminal*", "work"),
        ("file*", "work"),
        ("cron*", "automation"),
    )

    def __init__(self, rules: Sequence[tuple[str, RoomId]]) -> None:
        self._rules = (*rules, *self.DEFAULTS)

    def resolve(self, tool_name: str) -> RoomId:
        """Return the first matching room or the conservative work fallback."""
        for pattern, room in self._rules:
            if fnmatch(tool_name, pattern):
                return room
        return "work"
