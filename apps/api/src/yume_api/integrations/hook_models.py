"""Bounded, non-sensitive payloads accepted from Hermes event hooks."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

MAX_EVENT_ID_LENGTH = 256
MAX_SESSION_ID_LENGTH = 256
MAX_CHILD_SESSION_ID_LENGTH = 256
MAX_CHILD_SUBAGENT_ID_LENGTH = 256
MAX_CHILD_ROLE_LENGTH = 64
MAX_CHILD_GOAL_LENGTH = 1_000
MAX_CHILD_STATUS_LENGTH = 64
MAX_DURATION_MS = 604_800_000
MAX_TOOL_HISTORY_LENGTH = 100
MAX_TOOL_NAME_LENGTH = 128
MAX_TOOL_STATUS_LENGTH = 64
SAFE_EXTRA_LENGTHS = {
    "child_session_id": MAX_CHILD_SESSION_ID_LENGTH,
    "child_subagent_id": MAX_CHILD_SUBAGENT_ID_LENGTH,
    "child_role": MAX_CHILD_ROLE_LENGTH,
    "child_goal": MAX_CHILD_GOAL_LENGTH,
    "child_status": MAX_CHILD_STATUS_LENGTH,
}
SAFE_EXTRA_FIELDS = {*SAFE_EXTRA_LENGTHS, "duration_ms", "tool_call_history"}
UNSUPPORTED_EXTRA_FIELD_MESSAGE = "hook extra contains an unsupported field"
INVALID_EXTRA_VALUE_MESSAGE = "hook extra value is empty or exceeds its limit"
MISSING_STOP_STATUS_MESSAGE = "subagent stop requires child_status"


class HookToolCall(BaseModel):
    """One bounded, result-free summary of a completed tool invocation."""

    model_config = ConfigDict(extra="forbid")

    tool_name: Annotated[StrictStr, Field(min_length=1, max_length=MAX_TOOL_NAME_LENGTH)]
    status: Annotated[StrictStr, Field(min_length=1, max_length=MAX_TOOL_STATUS_LENGTH)]


type HookExtraValue = StrictStr | StrictInt | list[HookToolCall]


class HookEnvelope(BaseModel):
    """One allow-listed lifecycle event emitted by a configured Hermes hook."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    event_id: str = Field(min_length=1, max_length=MAX_EVENT_ID_LENGTH)
    occurred_at: datetime
    event: Literal["subagent_start", "subagent_stop"]
    session_id: str = Field(min_length=1, max_length=MAX_SESSION_ID_LENGTH)
    extra: dict[str, HookExtraValue] = Field(max_length=len(SAFE_EXTRA_FIELDS))

    @field_validator("extra")
    @classmethod
    def validate_extra(cls, extra: dict[str, HookExtraValue]) -> dict[str, HookExtraValue]:
        """Reject values that could carry credentials or raw tool output."""
        unsafe_keys = extra.keys() - SAFE_EXTRA_FIELDS
        if unsafe_keys:
            raise ValueError(UNSUPPORTED_EXTRA_FIELD_MESSAGE)
        for key, value in extra.items():
            if key in SAFE_EXTRA_LENGTHS and (
                not isinstance(value, str) or not value or len(value) > SAFE_EXTRA_LENGTHS[key]
            ):
                raise ValueError(INVALID_EXTRA_VALUE_MESSAGE)
            if key == "duration_ms" and (
                type(value) is not int or value < 0 or value > MAX_DURATION_MS
            ):
                raise ValueError(INVALID_EXTRA_VALUE_MESSAGE)
            if key == "tool_call_history" and (
                not isinstance(value, list) or len(value) > MAX_TOOL_HISTORY_LENGTH
            ):
                raise ValueError(INVALID_EXTRA_VALUE_MESSAGE)
        return extra

    @model_validator(mode="after")
    def validate_lifecycle_fields(self) -> Self:
        """Require the status needed to make a verified stop-state claim."""
        if self.event == "subagent_stop" and "child_status" not in self.extra:
            raise ValueError(MISSING_STOP_STATUS_MESSAGE)
        return self
