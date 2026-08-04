"""Bounded, non-sensitive payloads accepted from Hermes event hooks."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_EVENT_ID_LENGTH = 256
MAX_SESSION_ID_LENGTH = 256
MAX_CHILD_SUBAGENT_ID_LENGTH = 256
MAX_CHILD_ROLE_LENGTH = 64
MAX_CHILD_GOAL_LENGTH = 1_000
SAFE_EXTRA_LENGTHS = {
    "child_subagent_id": MAX_CHILD_SUBAGENT_ID_LENGTH,
    "child_role": MAX_CHILD_ROLE_LENGTH,
    "child_goal": MAX_CHILD_GOAL_LENGTH,
}
UNSUPPORTED_EXTRA_FIELD_MESSAGE = "hook extra contains an unsupported field"
INVALID_EXTRA_VALUE_MESSAGE = "hook extra value is empty or exceeds its limit"


class HookEnvelope(BaseModel):
    """One allow-listed lifecycle event emitted by a configured Hermes hook."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    event_id: str = Field(min_length=1, max_length=MAX_EVENT_ID_LENGTH)
    occurred_at: datetime
    event: Literal["subagent_start", "subagent_stop"]
    session_id: str = Field(min_length=1, max_length=MAX_SESSION_ID_LENGTH)
    extra: dict[str, str] = Field(max_length=len(SAFE_EXTRA_LENGTHS))

    @field_validator("extra")
    @classmethod
    def validate_extra(cls, extra: dict[str, str]) -> dict[str, str]:
        """Reject values that could carry credentials or raw tool output."""
        unsafe_keys = extra.keys() - SAFE_EXTRA_LENGTHS.keys()
        if unsafe_keys:
            raise ValueError(UNSUPPORTED_EXTRA_FIELD_MESSAGE)
        for key, value in extra.items():
            if not value or len(value) > SAFE_EXTRA_LENGTHS[key]:
                raise ValueError(INVALID_EXTRA_VALUE_MESSAGE)
        return extra
