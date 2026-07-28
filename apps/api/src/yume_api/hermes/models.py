from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

type HermesIdentifier = Annotated[StrictStr, Field(min_length=1)]


class HermesCapabilities(BaseModel):
    """Runtime features advertised by a Hermes Gateway instance."""

    model_config = ConfigDict(extra="ignore")

    session_chat_stream: StrictBool = False
    run_submission: StrictBool = False
    run_status: StrictBool = False
    run_events_sse: StrictBool = False
    run_stop: StrictBool = False
    run_approval: StrictBool = False


class HermesCapabilitiesResponse(BaseModel):
    """Wire response returned by the Hermes capabilities endpoint."""

    model_config = ConfigDict(extra="ignore")

    features: HermesCapabilities


class HermesStreamEvent(BaseModel):
    """One decoded server-sent event from Hermes."""

    event: StrictStr
    data: dict[str, Any]


class HermesRun(BaseModel):
    """A Hermes compatibility run and its current terminal state."""

    model_config = ConfigDict(extra="ignore")

    run_id: HermesIdentifier
    status: Literal[
        "started",
        "running",
        "waiting_approval",
        "stopping",
        "completed",
        "failed",
        "cancelled",
    ]
    output: str | None = None
    error: str | None = None


class HermesSessionCreated(BaseModel):
    """Wire response returned when Hermes creates a persistent session."""

    model_config = ConfigDict(extra="ignore")

    id: HermesIdentifier


class HermesJob(BaseModel):
    """Wire representation of one persistent Hermes scheduled job."""

    model_config = ConfigDict(extra="ignore")

    id: HermesIdentifier
    name: str
    next_run_at: datetime | None = None


class HermesRunCreated(BaseModel):
    """Wire response returned when Hermes creates a compatibility run."""

    model_config = ConfigDict(extra="ignore")

    run_id: HermesIdentifier


class HermesContentPart(BaseModel):
    """One structured content part in a Hermes transcript message."""

    model_config = ConfigDict(extra="ignore")

    type: StrictStr
    text: str | None = None


class HermesSessionMessage(BaseModel):
    """Wire representation of a single Hermes transcript message."""

    model_config = ConfigDict(extra="ignore")

    id: HermesIdentifier
    role: Literal["user", "assistant"]
    content: str | list[HermesContentPart]
