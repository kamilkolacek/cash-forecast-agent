---
description: Write (or rewrite) the CFO memo for the latest forecast run
---

Use the `cfo-narrative` skill.

1. RUN is the directory named in `outputs/runs/LATEST`. If it has no `facts.md`, run
   `python scripts/run_weekly.py` first.
2. Read `RUN/facts.md`, plus `RUN/review.md` if present.
3. Write `RUN/memo.md` following `.claude/skills/cfo-narrative/templates/memo.md`.
4. If the traceability hook blocks the write, correct the figures from `facts.md` and
   write again. Confirm with `python scripts/check_memo.py`.
5. Reply with the memo path and its bottom-line paragraph.
