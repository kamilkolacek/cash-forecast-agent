---
description: Generate or refresh the synthetic Northwind Cloud dataset and validate it
argument-hint: "[--seed N] [--no-anomalies] [--csv]"
---

Generate the synthetic dataset and report on it.

1. Run `python scripts/generate.py $ARGUMENTS`.
2. If validation FAILED, show the failing ERROR checks and stop. Do not continue to a forecast.
3. Otherwise, summarize for a finance reader in a short table, using only figures printed by
   the script or present in `data/raw/manifest.json`:
   - ARR at as_of, active customers, billing mix
   - Cash at as_of and the historical low
   - Open AR
4. List each injected anomaly from the manifest and confirm which validation finding
   detected it (`dq:duplicate_ap_payment`, `dq:stale_undisputed_ar`, `dq:overdue_concentration`).
   Note any anomaly that no finding caught.

Never edit files in `data/raw/` by hand.
