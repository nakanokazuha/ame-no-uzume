"""Startup diagnostics that remain available when optional dependencies fail."""

from pathlib import Path
from typing import Literal, Self

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api")

DiagnosticStatus = Literal["ready", "invalid_config", "invalid_assets", "hermes_unavailable"]


class Diagnostic(BaseModel):
    """A browser-safe explanation of the dashboard's current availability."""

    status: DiagnosticStatus
    file: str | None = None
    message: str = ""

    @classmethod
    def ready(cls) -> Self:
        return cls(status="ready")

    @classmethod
    def invalid_config(cls, path: Path, error: Exception) -> Self:
        return cls(status="invalid_config", file=str(path), message=str(error))

    @classmethod
    def invalid_assets(cls, path: Path, error: Exception) -> Self:
        return cls(status="invalid_assets", file=str(path), message=str(error))

    @classmethod
    def hermes_unavailable(cls, error: Exception) -> Self:
        return cls(
            status="hermes_unavailable",
            message=(
                f"Hermes connection failed ({type(error).__name__}); verify the local API server."
            ),
        )


@router.get("/diagnostics")
def diagnostics(request: Request) -> Diagnostic:
    """Return the current startup state, including recoverable failures."""
    return request.app.state.diagnostic


@router.post("/diagnostics/retry")
async def retry_diagnostics(request: Request) -> Diagnostic:
    """Retry a recoverable Hermes startup connection without restarting the container."""
    return await request.app.state.retry_hermes()
