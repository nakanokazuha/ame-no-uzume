"""Tests for process-level production settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from yume_api.main import _runtime_paths
from yume_api.settings import Settings


def test_settings_requires_hermes_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Reject startup when the server-only Hermes credential is absent."""
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_redacts_hermes_api_key_in_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not expose the Hermes credential when settings are represented."""
    monkeypatch.setenv("HERMES_API_KEY", "super-secret")

    assert "super-secret" not in repr(Settings())


def test_runtime_paths_remain_source_tree_defaults_with_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local credential must not accidentally select container-only paths."""
    monkeypatch.setenv("HERMES_API_KEY", "local-development-key")
    monkeypatch.delenv("YUME_DASHBOARD_CONFIG", raising=False)
    monkeypatch.delenv("YUME_ASSET_PACK_ROOT", raising=False)
    monkeypatch.delenv("YUME_WEB_DIST", raising=False)

    assert _runtime_paths() == (
        Path("config/dashboard.example.yaml"),
        Path("asset-packs"),
        Path("apps/web/dist"),
    )
