import pandas as pd

from cashforecast.config import load_yaml
from cashforecast.synthetic import customers
from cashforecast.synthetic._util import bday
from cashforecast.synthetic.generator import build_context
from cashforecast.synthetic.payables import next_payment_run
from cashforecast.synthetic.payroll import pay_dates


def test_bday_rolls_weekend_forward():
    assert bday(pd.Timestamp("2026-10-31")) == pd.Timestamp("2026-11-02")  # Sat -> Mon
    assert bday(pd.Timestamp("2026-11-04")) == pd.Timestamp("2026-11-04")  # Wed stays


def test_payment_runs_land_on_tue_or_fri():
    for day in pd.date_range("2026-11-01", periods=14):
        assert next_payment_run(day, [1, 4]).weekday() in (1, 4)


def test_biweekly_payroll_is_fridays_26_per_year():
    dates = pay_dates("biweekly", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31"))
    assert all(d.weekday() == 4 for d in dates)
    assert len(dates) in (26, 27)


def test_semimonthly_payroll_count():
    dates = pay_dates("semimonthly", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31"))
    assert len(dates) == 24


def test_generation_is_deterministic_for_a_seed():
    cfg = load_yaml("company.yaml")
    a, _ = customers.generate_customers(build_context(cfg, seed=7))
    b, _ = customers.generate_customers(build_context(cfg, seed=7))
    c, _ = customers.generate_customers(build_context(cfg, seed=8))
    pd.testing.assert_frame_equal(a, b)
    assert not a["arr"].equals(c["arr"])


def test_whales_carry_target_arr_share():
    cfg = load_yaml("company.yaml")
    df, _ = customers.generate_customers(build_context(cfg))
    existing = df[df["origin"] == "existing"]
    share = existing.loc[existing["is_whale"], "arr"].sum() / existing["arr"].sum()
    assert abs(share - cfg["customers"]["whales"]["arr_share"]) < 1e-9
