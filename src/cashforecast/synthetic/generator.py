"""Orchestrate the full synthetic dataset: simulate, inject anomalies, split at as_of, write."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cashforecast.config import load_yaml
from cashforecast.synthetic import anomalies, bank, customers, debt_capex_tax, payables, payroll
from cashforecast.synthetic import receivables as ar
from cashforecast.synthetic._util import SimContext
from cashforecast.synthetic.fx import FxTable, generate_fx


def build_context(cfg: dict[str, Any], seed: int | None = None) -> SimContext:
    sim = cfg["simulation"]
    as_of = pd.Timestamp(sim["as_of"])
    return SimContext(
        cfg=cfg,
        rng=np.random.default_rng(sim["seed"] if seed is None else seed),
        start=pd.Timestamp(sim["history_start"]),
        as_of=as_of,
        end=as_of + pd.Timedelta(weeks=sim["holdout_weeks"]) - pd.Timedelta(days=1),
    )


def simulate(ctx: SimContext, inject: bool = True) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """Simulate the whole window (history + holdout) as if it were all actuals."""
    fx_df = generate_fx(ctx)
    fx = FxTable(fx_df)
    cust, _ = customers.generate_customers(ctx)
    contracts = customers.generate_contracts(ctx, cust)
    pipeline = customers.generate_pipeline(ctx, cust, contracts)
    invoices = ar.generate_invoices(ctx, cust, contracts, fx)
    invoices, receipts = ar.simulate_receipts(ctx, cust, invoices, fx)
    months = pd.date_range(ctx.start, ctx.end, freq="MS")
    arr = ar.arr_by_month(contracts, months)
    vendors = payables.generate_vendors(ctx)
    bills, ap_payments = payables.generate_bills(ctx, vendors, arr, fx)
    d = dict(
        fx_rates=fx_df,
        customers=cust,
        contracts=contracts,
        pipeline=pipeline,
        invoices=invoices,
        receipts=receipts,
        vendors=vendors,
        ap_bills=bills,
        ap_payments=ap_payments,
        payroll=payroll.generate_payroll(ctx, arr, fx),
        commissions=payroll.generate_commissions(ctx, ar.bookings_by_month(contracts)),
        debt_schedule=debt_capex_tax.generate_debt_schedule(ctx),
        capex=debt_capex_tax.generate_capex(ctx),
        taxes=debt_capex_tax.generate_taxes(ctx, invoices),
        arr_monthly=arr.rename("arr_usd").rename_axis("month").reset_index(),
    )
    injected = anomalies.inject(ctx, d, ctx.cfg.get("anomalies", [])) if inject else []
    d["bank_transactions"] = bank.build_ledger(ctx, d)
    return d, injected


def split(ctx: SimContext, d: dict[str, pd.DataFrame]) -> tuple[dict, dict]:
    """History (known at as_of) vs holdout (future actuals hidden from the forecaster)."""
    a = ctx.as_of
    hist, hold = {}, {}

    def cut(name: str, col: str) -> None:
        df = d[name]
        hist[name] = df[df[col] < a].reset_index(drop=True)
        hold[name] = df[df[col] >= a].reset_index(drop=True)

    for name, col in [
        ("fx_rates", "date"),
        ("receipts", "receipt_date"),
        ("ap_payments", "payment_date"),
        ("payroll", "pay_date"),
        ("commissions", "pay_date"),
        ("bank_transactions", "date"),
    ]:
        cut(name, col)

    cust = d["customers"]
    hist["customers"] = (
        cust[cust["first_start"] < a].drop(columns=["origin"]).reset_index(drop=True)
    )
    hold["customers_future"] = cust[cust["first_start"] >= a].reset_index(drop=True)

    k = d["contracts"]
    hk = k[k["term_start"] < a].copy()
    hk["churned_at_end"] = hk["churned_at_end"].where(hk["term_end"] < a)  # future churn unknown
    hist["contracts"] = hk.drop(columns=["billing_delay_days"]).reset_index(drop=True)
    hold["contracts"] = k.reset_index(drop=True)

    inv = d["invoices"]
    hinv = inv[inv["issue_date"] < a].copy()
    paid = hist["receipts"].groupby("invoice_id")["amount_local"].sum()
    hinv["paid_local_to_date"] = hinv["invoice_id"].map(paid).fillna(0.0).round(2)
    hinv["open_amount_local"] = (hinv["amount_local"] - hinv["paid_local_to_date"]).round(2)
    wo = hinv["written_off_date"] < a
    hinv["status"] = np.where(
        wo, "written_off", np.where(hinv["open_amount_local"] <= 0.005, "paid", "open")
    )
    hinv["written_off_date"] = hinv["written_off_date"].where(wo)
    hist["invoices"] = hinv.reset_index(drop=True)
    hold["invoices"] = inv[inv["issue_date"] >= a].reset_index(drop=True)

    bills = d["ap_bills"]
    hb = bills[bills["issue_date"] < a].copy()
    paid_b = hist["ap_payments"].groupby("bill_id")["amount_local"].sum()
    hb["paid_local_to_date"] = hb["bill_id"].map(paid_b).fillna(0.0).round(2)
    hb["status"] = np.where(hb["paid_local_to_date"] >= hb["amount_local"] - 0.005, "paid", "open")
    hist["ap_bills"] = hb.reset_index(drop=True)
    hold["ap_bills"] = bills[bills["issue_date"] >= a].reset_index(drop=True)

    pipe = d["pipeline"]
    hist["pipeline"] = pipe.drop(columns=["outcome", "actual_close"])
    hold["pipeline_outcomes"] = pipe[["opportunity_id", "outcome", "actual_close"]]

    cx = d["capex"].copy()
    hold["capex_actuals"] = cx[cx["actual_date"] >= a].reset_index(drop=True)
    cx["actual_date"] = cx["actual_date"].where(cx["actual_date"] < a)
    hist["capex_plan"] = cx

    tax = d["taxes"].copy()
    tax["paid"] = tax["due_date"] < a
    hist["tax_calendar"] = tax

    am = d["arr_monthly"]
    hist["arr_monthly"] = am[am["month"] < a].reset_index(drop=True)
    for name in ("vendors", "debt_schedule"):  # reference data and contractual schedules
        hist[name] = d[name]

    opening = ctx.cfg["balance_sheet"]["opening_cash"]
    balances = bank.daily_balances(d["bank_transactions"], opening, ctx.start, ctx.end)
    hist["bank_balances"] = balances[balances["date"] < a].reset_index(drop=True)
    hold["bank_balances"] = balances[balances["date"] >= a].reset_index(drop=True)
    return hist, hold


def summarize(ctx: SimContext, hist: dict, hold: dict, injected: list[dict]) -> dict[str, Any]:
    k = hist["contracts"]
    a = ctx.as_of
    active = k[(k["term_start"] <= a) & (k["term_end"] >= a)]
    mix = (active.groupby("billing_freq")["arr_usd"].sum() / active["arr_usd"].sum()).round(3)
    bal = hist["bank_balances"]
    lo = bal.loc[bal["closing_balance_usd"].idxmin()]
    return {
        "company": ctx.cfg["company"]["name"],
        "seed": int(ctx.cfg["simulation"]["seed"]),
        "history_start": str(ctx.start.date()),
        "as_of": str(a.date()),
        "holdout_end": str(ctx.end.date()),
        "arr_at_history_start_usd": round(float(hist["arr_monthly"]["arr_usd"].iloc[0]), 0),
        "arr_at_as_of_usd": round(float(active["arr_usd"].sum()), 0),
        "active_customers_at_as_of": int(active["customer_id"].nunique()),
        "billing_mix_by_arr": mix.to_dict(),
        "cash_at_as_of_usd": float(bal["closing_balance_usd"].iloc[-1]),
        "min_cash_in_history_usd": float(lo["closing_balance_usd"]),
        "min_cash_date": str(lo["date"].date()),
        "open_ar_usd_at_issue": round(
            float(
                hist["invoices"]
                .loc[hist["invoices"]["status"] == "open", "amount_usd_at_issue"]
                .sum()
            ),
            0,
        ),
        "row_counts": {
            "history": {k: len(v) for k, v in hist.items()},
            "holdout": {k: len(v) for k, v in hold.items()},
        },
        "anomalies": injected,
    }


def generate(
    out_dir: Path,
    seed: int | None = None,
    inject: bool = True,
    csv: bool = False,
    config_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = load_yaml("company.yaml", config_dir) if config_dir else load_yaml("company.yaml")
    if seed is not None:
        cfg["simulation"]["seed"] = seed
    ctx = build_context(cfg)
    data, injected = simulate(ctx, inject=inject)
    hist, hold = split(ctx, data)
    out_dir = Path(out_dir)
    (out_dir / "holdout").mkdir(parents=True, exist_ok=True)
    for folder, tables in ((out_dir, hist), (out_dir / "holdout", hold)):
        for name, df in tables.items():
            df.to_parquet(folder / f"{name}.parquet", index=False)
            if csv:
                df.to_csv(folder / f"{name}.csv", index=False)
    manifest = summarize(ctx, hist, hold, injected)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest
