from pathlib import Path

import yaml

from yume_api.config.models import DashboardConfig


def load_dashboard_config(path: Path) -> DashboardConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return DashboardConfig.model_validate(data or {})
