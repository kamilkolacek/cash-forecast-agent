"""Load and validate project configuration from config/*.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


class ForecastSettings(BaseModel):
    horizon_weeks: int = Field(ge=1, le=52)
    daily_detail_weeks: int = Field(ge=0)
    week_start: str
    reporting_currency: str
    min_cash_threshold: float = Field(ge=0)
    revolver_auto_draw: bool = False

    @model_validator(mode="after")
    def daily_within_horizon(self) -> ForecastSettings:
        if self.daily_detail_weeks > self.horizon_weeks:
            raise ValueError("daily_detail_weeks cannot exceed horizon_weeks")
        return self


class Entity(BaseModel):
    code: str
    name: str
    currency: str
    arr_share: float = Field(gt=0, le=1)


def load_yaml(name: str, config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    with open(config_dir / name, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{name} must contain a mapping at the top level")
    return data


def load_forecast_settings(config_dir: Path = CONFIG_DIR) -> ForecastSettings:
    return ForecastSettings(**load_yaml("forecast.yaml", config_dir)["forecast"])


def load_entities(config_dir: Path = CONFIG_DIR) -> list[Entity]:
    entities = [Entity(**e) for e in load_yaml("company.yaml", config_dir)["entities"]]
    total = sum(e.arr_share for e in entities)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"entity arr_share must sum to 1.0, got {total}")
    return entities
