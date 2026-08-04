"""Authentication and bounded replay protection for Hermes hook events."""

import hmac

from cachetools import TTLCache

from yume_api.integrations.hook_models import HookEnvelope

MAX_SEEN_EVENT_IDS = 10_000
SEEN_EVENT_TTL_SECONDS = 3_600
INVALID_HOOK_AUTH_MESSAGE = "invalid hook token"


class HookReceiver:
    """Authenticate and acknowledge each configured hook event at most once."""

    def __init__(self, expected_token: str) -> None:
        self._token = expected_token
        self._seen: TTLCache[str, bool] = TTLCache(
            maxsize=MAX_SEEN_EVENT_IDS, ttl=SEEN_EVENT_TTL_SECONDS
        )

    def authenticate(self, token: str) -> None:
        """Require a constant-time match against the server-side hook secret."""
        if not hmac.compare_digest(token, self._token):
            raise PermissionError(INVALID_HOOK_AUTH_MESSAGE)

    def accept(self, envelope: HookEnvelope) -> bool:
        """Return whether this event ID has not already been acknowledged."""
        if envelope.event_id in self._seen:
            return False
        self._seen[envelope.event_id] = True
        return True
