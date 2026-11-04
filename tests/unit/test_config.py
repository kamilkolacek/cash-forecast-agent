from pathlib import Path

import pytest
import yaml

from cashforecast import __version__
from cashforecast.config import (
    ForecastSettings,
    load_entities,
    load_forecast_settings,
    load_yaml,
)


def test_version() -> None:
    assert __version__ == "1.0.0"


def test_forecast_settings_load() -> None:
    s = load_forecast_settings()
    assert s.horizon_weeks == 13
    assert s.daily_detail_weeks == 2
    assert s.reporting_currency == "USD"


def test_entities_sum_to_one() -> None:
    entities = load_entities()
    assert {e.code for e in entities} == {"US01", "UK01", "CA01"}


def test_daily_weeks_cannot_exceed_horizon() -> None:
    with pytest.raises(ValueError):
        ForecastSettings(
            horizon_weeks=4,
            daily_detail_weeks=5,
            week_start="Monday",
            reporting_currency="USD",
            min_cash_threshold=0,
        )


def test_all_config_files_parse() -> None:
    for name in ["company.yaml", "forecast.yaml", "scenarios.yaml", "categories.yaml"]:
        assert isinstance(load_yaml(name), dict)


def test_bad_entity_shares_rejected(tmp_path: Path) -> None:
    bad = {"entities": [{"code": "X", "name": "X", "currency": "USD", "arr_share": 0.5}]}
    (tmp_path / "company.yaml").write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError):
        load_entities(tmp_path)
