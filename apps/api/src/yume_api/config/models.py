import re

from pydantic import BaseModel, Field, field_validator

from yume_api.contracts.events import RoomId


class RoomRule(BaseModel):
    pattern: str
    room: RoomId

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as error:
            msg = f"invalid regular expression: {error}"
            raise ValueError(msg) from error
        return value


class DashboardConfig(BaseModel):
    asset_pack: str = "placeholder"
    hermes_base_url: str = "http://127.0.0.1:8642"
    data_dir: str = "/data"
    room_rules: list[RoomRule] = Field(default_factory=list)
