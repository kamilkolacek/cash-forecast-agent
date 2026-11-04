---
description: Run a named or custom cash scenario against the latest forecast
argument-hint: "<scenario name | plain-English what-if>"
---

Use the `treasury-risk` skill.

The request is: $ARGUMENTS

1. If it names a scenario in `config/scenarios.yaml` (or says "all"), run
   `python scripts/run_scenario.py --name <name>` (no flag for all).
2. Otherwise translate the what-if into shocks using the types documented at the top of
   `config/scenarios.yaml`. State the shocks you chose and any assumption you had to make
   (date, amount, which customers). Run
   `python scripts/run_scenario.py --custom <short_snake_case_name> '<shocks JSON>'`.
3. Report against base: ending cash, change vs base, minimum cash and date, headroom to
   the floor and covenant, flagged weeks, and suggested revolver draw. Recommend an
   action only if headroom is thin or negative.
4. Quote figures exactly as printed or from `scenarios.json`.
