#!/usr/bin/env python3
"""Task-log appender — append ONE finished-task row to docs/BACKLOG.md.

BACKLOG.md is the LOG (append-only, for tracing back), NOT the source of truth
(that's SoT.md) and NOT the live board (that's TaskBoard.md). When a task is marked
complete, a PostToolUse hook builds a tiny JSON event from the task's TaskBoard card
and pipes it here; this script formats + appends it — so the file is NEVER read into
context (zero context cost) and the row format can't drift. (Runnable by hand too,
for a backfill.)

Usage:
    echo '{"task_id":"3","dept":"RnD","task":"login form","status":"done",
           "sha":"abc1234","note":"42 tests green"}' | python3 log.py [docs/BACKLOG.md]

Fields (all optional except task_id is recommended): task_id, dept, task,
status (done|partial|dropped), sha, note, date (defaults to today).
"""
import sys, json, os
from datetime import datetime

HEADER = (
    "# BACKLOG — finished-task log\n\n"
    "> Append-only · for tracing back · **NOT** the source of truth.\n"
    "> Source of truth = `SoT.md` · live tasks = `TaskBoard.md`. Finished tasks land here.\n"
    "> Auto-written on task-completion (a PostToolUse hook, via `log.py`) — don't hand-edit; format is code-guaranteed.\n\n"
    "| date | id | dept | task | status | sha | note |\n"
    "|---|---|---|---|---|---|---|\n"
)


def cell(v):
    return str(v if v not in (None, "") else "—").replace("|", "\\|").replace("\n", " ").strip()


def row(d, date):
    return "| %s | %s | %s | %s | %s | %s | %s |\n" % (
        date, cell(d.get("task_id")), cell(d.get("dept")), cell(d.get("task")),
        cell(d.get("status", "done")), cell(d.get("sha")), cell(d.get("note")))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "docs/BACKLOG.md"
    d = json.load(sys.stdin)
    date = d.get("date") or datetime.now().strftime("%Y-%m-%d")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fresh = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8") as f:
        if fresh:
            f.write(HEADER)
        f.write(row(d, date))
    sys.stdout.write("logged task %s → %s\n" % (d.get("task_id", "?"), path))


if __name__ == "__main__":
    main()
