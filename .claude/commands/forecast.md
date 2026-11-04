---
description: Full weekly cash forecast cycle - validate, forecast, variance, scenarios, independent review, CFO memo
argument-hint: "[--simulate-week N]"
---

Run the weekly cash forecast end to end. Use the `cash-forecasting`, `variance-analysis`,
`treasury-risk` and `cfo-narrative` skills.

1. **Validate.** Use the `data-validator` subagent. If its verdict is FAIL, stop and report.
2. **Run the engine.** `python scripts/run_weekly.py $ARGUMENTS`. The last line printed
   is the run directory; call it RUN.
3. **Independent review.** Use the `forecast-reviewer` subagent on RUN. It writes
   `RUN/review.md`.
4. **Write the memo.** Read `RUN/facts.md` and `RUN/review.md`, then write `RUN/memo.md`
   using the `cfo-narrative` template. Address every HIGH review finding. Include the
   data-validator's action items under Risks and actions.
5. **Traceability.** A hook checks every figure in `memo.md` when you write it. If it
   blocks, fix the figures from `facts.md` and write again. Finish by running
   `python scripts/check_memo.py` and confirming it passes.
6. **Report back** in under 120 words: ending cash, low point, any flags, the biggest
   variance driver, the reviewer's verdict, and the memo path.

Never state a figure that isn't in the run artifacts.
