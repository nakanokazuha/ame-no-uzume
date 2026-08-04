"""Tests for process-level production settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from yume_api.assets.validator import load_and_validate_pack
from yume_api.config.loader import load_dashboard_config
from yume_api.main import _build_runtime, _runtime_paths
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


def test_settings_configures_hook_runtime_from_yume_hook_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the explicitly named operator environment variable for the hook bridge."""
    monkeypatch.setenv("HERMES_API_KEY", "hermes-secret")
    monkeypatch.setenv("YUME_HOOK_TOKEN", "configured-hook-secret")
    monkeypatch.setenv("HOOK_TOKEN", "wrong-token-name")

    settings = Settings()
    config = load_dashboard_config(Path("config/dashboard.example.yaml"))
    asset_pack = load_and_validate_pack(Path("asset-packs") / config.asset_pack)
    runtime = _build_runtime(config, asset_pack)

    assert settings.hook_token is not None
    assert settings.hook_token.get_secret_value() == "configured-hook-secret"
    assert runtime.hook_token is not None
    assert runtime.hook_token.get_secret_value() == "configured-hook-secret"
    assert "configured-hook-secret" not in repr(settings)


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
