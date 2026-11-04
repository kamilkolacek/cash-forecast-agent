"""End-to-end checks on a freshly generated dataset (generated once per test session)."""

from __future__ import annotations

import pandas as pd


def _finding(report, check):
    return next(f for f in report["findings"] if f["check"] == check)


def test_all_tieouts_pass(dataset):
    _, _, _, report = dataset
    failed = [
        f["check"] for f in report["findings"] if f["severity"] == "ERROR" and not f["passed"]
    ]
    assert failed == []


def test_whale_late_payment_detected(dataset):
    _, _, m, report = dataset
    a = next(x for x in m["anomalies"] if x["type"] == "whale_late_payment")
    flagged = {
        r["invoice_id"] for r in _finding(report, "dq:payment_behavior_break")["data"]["invoices"]
    }
    assert a["invoice_id"] in flagged


def test_customer_default_detected(dataset):
    _, _, m, report = dataset
    a = next(x for x in m["anomalies"] if x["type"] == "customer_default")
    flagged = {
        r["customer_id"] for r in _finding(report, "dq:payment_behavior_break")["data"]["invoices"]
    }
    assert a["customer_id"] in flagged


def test_duplicate_payment_detected(dataset):
    _, _, m, report = dataset
    a = next(x for x in m["anomalies"] if x["type"] == "duplicate_ap_payment")
    f = _finding(report, "dq:duplicate_ap_payment")
    assert not f["passed"]
    assert a["bill_id"] in {b["bill_id"] for b in f["data"]["bills"]}


def test_no_future_leakage(dataset):
    d, _, m, _ = dataset
    as_of = pd.Timestamp(m["as_of"])
    for table, col in [
        ("receipts", "receipt_date"),
        ("ap_payments", "payment_date"),
        ("bank_transactions", "date"),
        ("payroll", "pay_date"),
        ("invoices", "issue_date"),
        ("fx_rates", "date"),
    ]:
        assert d[table][col].max() < as_of, table
    k = d["contracts"]
    assert k.loc[k["term_end"] >= as_of, "churned_at_end"].isna().all()
    assert "outcome" not in d["pipeline"].columns
    assert d["capex_plan"]["actual_date"].dropna().max() < as_of


def test_holdout_continues_bank_balance(dataset):
    d, hold, _, _ = dataset
    last = d["bank_balances"]["closing_balance_usd"].iloc[-1]
    first = hold["bank_balances"]["opening_balance_usd"].iloc[0]
    assert abs(last - first) < 0.01


def test_company_shape_is_realistic(dataset):
    _, _, m, _ = dataset
    assert 230e6 < m["arr_at_as_of_usd"] < 275e6
    assert 0.55 < m["billing_mix_by_arr"]["annual"] < 0.72
    assert m["min_cash_in_history_usd"] > 30e6  # never breaches the covenant
    assert m["cash_at_as_of_usd"] > 35e6
