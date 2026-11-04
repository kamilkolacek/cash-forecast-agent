---
name: cfo-narrative
description: Structure, tone and number-traceability rules for the weekly CFO cash memo. Use when writing memo.md for /forecast or /cash-memo.
---

# CFO cash memo

Write `memo.md` into the run directory, following `templates/memo.md` in this skill.

## Rules

1. **Every figure comes from `facts.md`, as written.** A PostToolUse hook checks every
   `$` amount and `%` in `memo.md` against the run's artifacts and blocks the write if
   any figure is missing. If it blocks you, replace the figure with the one in
   `facts.md` (or remove it). Never round differently or compute a new total.
2. **Lead with the answer.** The first two sentences: where cash ends, the low point,
   and whether any action is needed.
3. **Explain, don't list.** For each driver, say why, not only how much.
4. **Timing vs permanent** must be explicit for every variance you mention.
5. **One page.** Around 350–450 words. Tables only where they replace sentences.
6. **Plain business English.** No engine jargon ("credibility-weighted", "quintile").
   Say "based on how this customer usually pays".
7. **Name customers by ID** (data is synthetic) and say if they are a whale.
8. **Risks and actions are specific**: who should do what, by when.

## Before writing

- Read `facts.md` fully.
- If `review.md` exists in the run directory (from the forecast-reviewer subagent),
  address every item marked HIGH in the memo or explain why it doesn't change the view.
