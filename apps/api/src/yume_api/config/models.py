from pydantic import BaseModel, Field


class RoomRule(BaseModel):
    pattern: str
    room: str


class DashboardConfig(BaseModel):
    asset_pack: str = "placeholder"
    hermes_base_url: str = "http://127.0.0.1:8642"
    data_dir: str = "/data"
    room_rules: list[RoomRule] = Field(default_factory=list)
