from yume_api.domain.room_policy import RoomPolicy


def test_resolve_uses_first_matching_custom_rule() -> None:
    policy = RoomPolicy([("web_*", "automation"), ("web_search", "memory")])

    assert policy.resolve("web_search") == "automation"


def test_resolve_applies_ordered_default_rules() -> None:
    policy = RoomPolicy([])

    assert policy.resolve("memory_search") == "memory"
    assert policy.resolve("web_search") == "research"
    assert policy.resolve("browser_open") == "research"
    assert policy.resolve("terminal_exec") == "work"
    assert policy.resolve("file_read") == "work"
    assert policy.resolve("cron_list") == "automation"


def test_resolve_unknown_tool_to_safe_work_room() -> None:
    policy = RoomPolicy([])

    assert policy.resolve("brand_new_tool") == "work"
