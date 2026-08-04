"""Environment-backed settings for the production dashboard process."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Keep container paths and the Hermes credential server-side."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    hermes_api_key: SecretStr
    hook_token: SecretStr | None = Field(default=None, validation_alias="YUME_HOOK_TOKEN")
    hermes_base_url: str = "http://127.0.0.1:8642"
    dashboard_config: Path = Path("/config/dashboard.yaml")
    asset_pack_root: Path = Path("/asset-packs")
    data_dir: Path = Path("/data")
    web_dist: Path = Path("/app/web")
