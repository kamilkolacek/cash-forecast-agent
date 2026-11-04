"""Forecast engine: balance identities, no leakage, anomaly handling, and accuracy."""

from __future__ import annotations

import json

import pandas as pd

from cashforecast.backtest.walk_forward import check_targets, run_backtest
from cashforecast.config import load_yaml
from cashforecast.engine.snapshot import take_snapshot


def test_rollforward_balances_every_day(live_forecast):
    r = live_forecast
    d = r.daily
    assert abs(d["opening_balance_usd"].iloc[0] - r.summary["opening_cash_usd"]) < 0.01
    prev_close = d["closing_balance_usd"].shift(1).iloc[1:]
    assert (abs(d["opening_balance_usd"].iloc[1:] - prev_close) < 0.01).all()
    assert (
        abs(
            r.summary["opening_cash_usd"]
            + r.lines["amount_usd"].sum()
            - r.summary["ending_cash_usd"]
        )
        < 0.01
    )


def test_weekly_view_ties_to_daily(live_forecast):
    w = live_forecast.weekly.set_index("line")
    weeks = [c for c in live_forecast.weekly.columns if c.startswith("W")]
    assert len(weeks) == 13
    sections = [
        "Total receipts",
        "Total operating disbursements",
        "Total non-operating disbursements",
        "Total financing",
    ]
    for wk in weeks:
        assert abs(w.loc[sections, wk].sum() - w.loc["Net cash flow", wk]) < 0.01
        assert (
            abs(w.loc["Opening cash", wk] + w.loc["Net cash flow", wk] - w.loc["Closing cash", wk])
            < 0.01
        )
    assert abs(w.loc["Closing cash", "W13"] - live_forecast.summary["ending_cash_usd"]) < 0.01


def test_daily_detail_covers_weeks_1_and_2(live_forecast):
    dd = live_forecast.daily_detail
    assert len(dd) == 14
    assert dd["date"].iloc[0] == live_forecast.as_of


def test_lines_stay_inside_horizon(live_forecast):
    r = live_forecast
    assert r.lines["date"].min() >= r.as_of
    assert r.lines["date"].max() <= pd.Timestamp(r.summary["horizon_end"])
    assert r.lines["source_id"].notna().all()


def test_snapshot_hides_the_future(dataset):
    d, _, m, _ = dataset
    cut = pd.Timestamp("2026-03-02")
    s = take_snapshot(d, cut, pd.Timestamp(m["as_of"]))
    assert s["receipts"]["receipt_date"].max() < cut
    assert s["invoices"]["issue_date"].max() < cut
    k = s["contracts"]
    assert k.loc[k["term_end"] >= cut, "churned_at_end"].isna().all()
    assert s.pipeline_reconstructed
    # An invoice paid after the cutoff must look open at the cutoff.
    late = d["receipts"][d["receipts"]["receipt_date"] >= cut]["invoice_id"]
    issued = s["invoices"][s["invoices"]["invoice_id"].isin(late)]
    assert (issued["status"] == "open").all()


def test_whale_anomaly_is_haircut_not_ignored(dataset, live_forecast):
    _, _, m, _ = dataset
    a = next(x for x in m["anomalies"] if x["type"] == "whale_late_payment")
    lines = live_forecast.lines[live_forecast.lines["source_id"] == a["invoice_id"]]
    assert len(lines) == 1
    assert "behavior break" in lines["note"].iloc[0]
    assert abs(lines["amount_usd"].iloc[0] / a["amount_usd"] - 0.5) < 0.05


def test_biweekly_payroll_continues_actual_cadence(dataset, live_forecast):
    d, _, _, _ = dataset
    last = d["payroll"].query("entity == 'US01' and component == 'net_pay'")["period_date"].max()
    us = live_forecast.lines[
        (live_forecast.lines["source_id"].str.startswith("US01:"))
        & (live_forecast.lines["category"] == "payroll_net")
    ]
    assert all(((x - last).days % 14 == 0) and x.weekday() == 4 for x in us["date"])


def test_assumptions_are_serializable(live_forecast):
    json.dumps(live_forecast.assumptions, default=str)
    r = live_forecast.assumptions["receipts"]["renewal_rates"]
    assert set(r["churn"]) == {"enterprise", "mid_market", "smb"}


def test_backtest_meets_closing_cash_targets(dataset):
    d, _, m, _ = dataset
    cfg = load_yaml("forecast.yaml")["backtest"]
    _, summary = run_backtest(d, pd.Timestamp(m["as_of"]), 13, cfg["min_training_weeks"])
    results = check_targets(summary, cfg["targets"])
    assert all(t["passed"] for t in results.values()), results
    # The engine must beat the naive baseline on closing cash.
    cb = summary["by_group"]["closing_balance"]
    assert cb["engine_weeks_5_13"] < cb["naive_weeks_5_13"]
