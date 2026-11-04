---
description: Run data tie-outs and data-quality checks on the current dataset
---

1. Run `python scripts/validate.py`.
2. Report ERROR checks first. Any failed ERROR means the dataset cannot be forecast; say so.
3. Then report WARNING findings as action items for treasury (who should do what),
   and INFO findings as context.
4. Quote amounts exactly as they appear in the output. Do not recompute or round them.
