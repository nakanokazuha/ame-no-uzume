from pathlib import Path

import pytest
from pydantic import ValidationError

from yume_api.config.loader import load_dashboard_config
from yume_api.config.models import RoomRule


def test_load_dashboard_config_parses_room_rules(tmp_path: Path) -> None:
    config_path = tmp_path / "dashboard.yaml"
    config_path.write_text(
        "asset_pack: studio\n"
        "hermes_base_url: http://127.0.0.1:9777\n"
        "data_dir: /var/lib/yume\n"
        "room_rules:\n"
        "  - pattern: '^browser\\.'\n"
        "    room: research\n",
        encoding="utf-8",
    )

    config = load_dashboard_config(config_path)

    assert config.asset_pack == "studio"
    assert config.hermes_base_url == "http://127.0.0.1:9777"
    assert config.data_dir == "/var/lib/yume"
    assert [(rule.pattern, rule.room) for rule in config.room_rules] == [
        ("^browser\\.", "research")
    ]


def test_example_dashboard_config_loads() -> None:
    config_path = Path(__file__).resolve().parents[4] / "config/dashboard.example.yaml"
    config = load_dashboard_config(config_path)

    assert config.asset_pack == "placeholder"
    assert config.hermes_base_url == "http://127.0.0.1:8642"
    assert [(rule.pattern, rule.room) for rule in config.room_rules] == [
        ("^memory\\.", "memory"),
        ("^browser\\.", "research"),
        ("^cron\\.", "automation"),
    ]


def test_room_rule_rejects_a_room_outside_the_shared_contract() -> None:
    with pytest.raises(ValidationError, match="room"):
        RoomRule.model_validate({"pattern": "^memory\\.", "room": "archive"})


def test_room_rule_rejects_malformed_regular_expressions() -> None:
    with pytest.raises(ValidationError, match="regular expression"):
        RoomRule(pattern="[unclosed", room="memory")
