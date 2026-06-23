---
description: Render the CEO morning brief (shipped / queued / needs-you) as a PDF/PNG and open it.
---

Produce the Boss's morning brief. From the current project state (`docs/TaskBoard.md`, `docs/BACKLOG.md`, and your latest run), gather three short lists — what **shipped**, what's **queued**, and what **needs the Boss's** decision — then render and open it:

```bash
echo '{"shipped":["…"],"queued":["…"],"needs_boss":["…"],"note":"…"}' | orchestrate-brief --pdf
```

Keep each field to short one-liners (the CEO authors the content; the script only formats it). Use `--png`, or omit the flag for HTML.

$ARGUMENTS
