"""Variance bridge identities, holdout timeline, scenarios and the facts sheet."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from cashforecast.data.timeline import combine_with_holdout
from cashforecast.engine.scenarios import run_scenarios, validate_shocks
from cashforecast.engine.variance import run_variance
from cashforecast.outputs.artifacts import (
    write_facts,
    write_forecast,
    write_scenarios,
    write_variance,
)
from cashforecast.outputs.traceability import untraceable


@pytest.fixture(scope="session")
def combined(dataset):
    d, hold, m, _ = dataset
    return combine_with_holdout(d, hold), pd.Timestamp(m["as_of"])


@pytest.fixture(scope="session")
def holdout_variance(combined):
    data, as_of = combined
    return run_variance(data, as_of, as_of + pd.Timedelta(weeks=4), as_of)


@pytest.fixture(scope="session")
def last_week_variance(dataset, live_forecast):
    d, _, m, _ = dataset
    as_of = pd.Timestamp(m["as_of"])
    return run_variance(d, as_of - pd.Timedelta(days=7), as_of, as_of)


@pytest.mark.parametrize("which", ["last_week_variance", "holdout_variance"])
def test_variance_identities(which, request):
    v = request.getfixturevalue(which)
    s, dr = v.summary, v.drivers
    # Drivers sum to the closing-cash difference.
    assert abs(dr["variance"].sum() - s["total_variance_usd"]) < 1.0
    assert (
        abs(s["actual_closing_cash_usd"] - s["forecast_closing_cash_usd"] - s["total_variance_usd"])
        < 0.02
    )
    # Timing + permanent = variance, per driver and in total.
    assert (abs(dr["timing"] + dr["permanent"] - dr["variance"]) < 0.02).all()
    assert abs(s["timing_usd"] + s["permanent_usd"] - s["total_variance_usd"]) < 1.0
    # Permanent total = revised minus prior-forecast cash at the comparison end.
    moved = s["revised_cash_at_comparison_end_usd"] - s["prior_forecast_cash_at_comparison_end_usd"]
    assert abs(moved - s["permanent_usd"]) < 1.0


def test_whale_anomaly_shows_as_permanent_favorable(dataset, holdout_variance):
    _, _, m, _ = dataset
    a = next(x for x in m["anomalies"] if x["type"] == "whale_late_payment")
    row = holdout_variance.drivers.set_index("driver").loc[a["customer_id"]]
    # Forecast haircut it to 50%; it paid in full inside the window.
    assert row["permanent"] > 0.4 * a["amount_usd"]
    assert row["is_whale"]


def test_timeline_reveals_holdout_only_after_cutoff(dataset, combined):
    d, _, _, _ = dataset
    data, as_of = combined
    assert data["bank_transactions"]["date"].max() > as_of
    from cashforecast.engine.snapshot import take_snapshot

    s = take_snapshot(data, as_of, as_of)
    assert len(s["receipts"]) == len(d["receipts"])


def test_scenarios_move_cash_in_the_expected_direction(dataset, live_forecast):
    d = dataset[0]
    s = run_scenarios(live_forecast, d)["scenarios"]
    assert s["base"]["change_vs_base_usd"] == 0
    for name in ("downside", "severe_downside", "churn_shock"):
        assert s[name]["ending_cash_usd"] < s["base"]["ending_cash_usd"], name
    for name in ("upside", "hiring_freeze"):
        assert s[name]["ending_cash_usd"] > s["base"]["ending_cash_usd"], name
    assert s["severe_downside"]["min_cash_usd"] < s["downside"]["min_cash_usd"]


def test_custom_one_off_breaching_floor_suggests_draw(dataset, live_forecast):
    shock = [
        {"type": "one_off", "date": "2026-12-15", "amount_usd": -30_000_000, "category": "capex"}
    ]
    r = run_scenarios(live_forecast, dataset[0], names=["base"], custom={"acq": shock})
    acq = r["scenarios"]["acq"]
    assert abs(acq["change_vs_base_usd"] + 30_000_000) < 1
    assert any(f["level"] == "below_internal_floor" for f in acq["flags"])
    assert acq["suggested_revolver_draw_usd"] > 0
    assert acq["suggested_revolver_draw_usd"] % 1_000_000 == 0


def test_bad_shocks_rejected():
    with pytest.raises(ValueError):
        validate_shocks([{"type": "meteor"}])
    with pytest.raises(ValueError):
        validate_shocks([{"type": "churn"}])


def test_facts_sheet_and_traceability(tmp_path, dataset, live_forecast, last_week_variance):
    run = write_forecast(live_forecast, tmp_path)
    write_variance(run, last_week_variance)
    write_scenarios(run, run_scenarios(live_forecast, dataset[0]))
    facts = write_facts(run).read_text()
    for section in (
        "## Headline",
        "## Weekly view",
        "## Variance",
        "## Scenarios",
        "## Key assumptions",
    ):
        assert section in facts
    # Every figure on the facts sheet is, by definition, traceable.
    assert untraceable(facts, run) == []
    summary = json.loads((run / "summary.json").read_text())
    ending = f"${summary['ending_cash_usd'] / 1e6:.1f}M"
    assert untraceable(f"Cash ends at {ending}.", run) == []
    assert untraceable("Cash ends at $999.9M with 77.7% churn.", run) == ["$999.9M", "77.7%"]
