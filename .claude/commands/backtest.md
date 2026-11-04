---
description: Walk-forward accuracy report for the forecast engine
---

1. Run `python scripts/run_backtest.py`.
2. Report whether the formal targets (closing-cash WAPE) passed, quoting the printed values.
3. Explain accuracy by component in plain terms:
   - Weekly WAPE shows timing error; cumulative-flow WAPE shows whether totals are right.
   - Call out components where the engine is not clearly better than the naive baseline,
     in the backtest or the live holdout.
4. Mention the printed note about reconstructed pipeline.
5. Quote percentages exactly as printed.
