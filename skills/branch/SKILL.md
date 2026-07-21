---
name: branch
description: 分公司 mode — run an EXTERNAL dept (orchestrate.json `external`, e.g. Marketing) as its own session on its own Claude account, syncing with the main office through the shared card store + mail lane. Trigger — 「分公司上班」 / "branch clocking in". NOT for internal depts (they run as teammates under orchestrate) and NOT the CEO role.
---
# 分公司 (branch office)

You (this session) = ONE external dept of an orchestrate project, running outside the CEO's team — own account, own browser, no SendMessage/no platform tasks across offices. The Boss sits in YOUR session for this lane's decisions. Sync = the repo: card store (`docs/board/`) + mail (`docs/board/mail/`) + git.

First run in a fresh checkout → follow `reference/setup.md` (accounts · Chrome profile · worktree · office marker), then return here.

## 上岗 (each session)

1. **Identity:** read `.claude/orchestrate.json` → `external`. Exactly one handle → that's you; several → ask the Boss which. Read your brief at **`<main>/.claude/agents/<handle>.md`** (role · 领域标杆 · owned files · Done) — org identity is SHARED state like cards/mail: read it at the MAIN checkout, never your branch's possibly-stale copy, so a Boss/CEO brief edit on main is live for you without waiting for a merge — and the dept SOP (`orchestrate-sop`) — it binds you EXCEPT where this file overrides (no CEO/Registrar/platform tasks in-session; report by mail, not SendMessage).
2. **Office check:** confirm you're in your worktree (`.claude/worktrees/<handle>`, branch `branch/<handle>`) and `.claude/office.json` there says `{"office": "<handle>"}` — that marker routes the mail nudge. Resolve the MAIN checkout root once: `git rev-parse --git-common-dir` → its parent dir = `<main>`. **Shared state lives in `<main>` — cards, mail, `docs/reviews/`, BACKLOG: read AND write them at `<main>/docs/...`** (same piercing the Auditor uses for pass markers); only product work happens in the worktree. Editing product files in main's checkout = racing the CEO's session; don't.
3. **Sweep mail:** `<main>/docs/board/mail/*.md` with `to:` you and `status: unread` → act or reply (a reply is a NEW note: `<YYYYMMDD-HHMM>-<you>-<slug>.md`, frontmatter `from` you · `to` CEO/Boss · `re: "#NNN"` or the replied-to note's filename · `time: "YYYY-MM-DD HH:MM"` · `status: unread`, body free prose), then flip the read one's `status: read`. A Stop nudge backs this sweep mechanically; don't rely on it.

## Work loop

4. **Claim:** your cards = `<main>/docs/board/*.md` with `dept:` = your handle. Pick by the card's `priority:` (P0 first, unset last), then `blocked_on: —` and the Boss's word; set that card file's `status: doing` (status only — `priority:` is Boss/CEO-owned). Your cards only — an internal dept's card or the digest (`TaskBoard.md`) is never yours to touch. No claimable card and no mail → ask the Boss or stop; never invent scope.
5. **Work:** owned files only; commit each step staging only owned paths (`git add <paths>`, never `-A`). Staff/experts as one-shot subagents per SOP; **never `name:` a spawn** (teammates are the main office's concept). Browser work loads via ToolSearch (`claude-in-chrome` skill first); **outward-facing actions (posting, replying publicly, sending anything) need the Boss's explicit OK in this session, per action.**
6. **产出审查 (hard gate, unchanged):** done → invoke the L2 审查官 yourself — `Agent(subagent_type:"clock-in:Auditor", no name)` with your output + review key **`x<NNN>`** (the card's durable number — external cards have no platform task_id) + your handle. PASS → it writes `docs/reviews/x<NNN>.pass`; FAIL → rework ONCE, then set the card `blocked` and mail the CEO (a 督察 复盘 is the main office's call). **Boss-signed content:** when the Boss signed the artefact's content in this session or by mail, cite the signature in the invocation (the mail file / where the signed text lives) — the review then scopes to transcription + bounds + traceability; signed content is canon, never re-litigated. The round still runs: a verdict certifies a tree, and her sign-off changed it.
7. **Ship (path-scoped self-merge):** with the `.pass` AND a diff touching only your owned paths AND `<main>`'s working tree clean → `git -C <main> merge --no-ff branch/<handle>`, then retire the card: move its note to `<main>/docs/board/done/` adding `status: done` · `shipped: <date>` · `sha: <short-sha>`, and append the BACKLOG row: `echo '{"task_id":"x<NNN>","dept":"<handle>","task":"#<NNN> <name>","sha":"<sha>"}' | orchestrate-log <main>/docs/BACKLOG.md`. Diff crosses your paths, or `<main>` is dirty → do NOT merge: mail the CEO with the branch + sha and set the card `review`.
8. **Needs-Boss:** present in-session → ask directly. Away → mail with `needs_boss: yes` + `PushNotification` (ToolSearch it) so her phone pings. Product-truth conflicts (your copy vs `SoT.md`) → mail the CEO; never edit SoT or another dept's domain.
9. **收工:** statuses true on your cards, mail the CEO a 4-line report (状态 / 改了什么 / 产物 / 待办·卡点), stop.

## Boundaries (hard)

- Never: platform task tools (TaskCreate/TaskUpdate/…) for board cards · editing `TaskBoard.md` · other depts' cards/files · `SoT.md`/`DECISIONS.md`/`CANON.md` (read-only for you) · named teammate spawns · merging a cross-path diff.
- 红线 paths (orchestrate.json `redlines`) need the Boss's 准 before editing, same as in-house.
- Stuck (ambiguous card, missing context, refused merge, 2nd L2 bounce) → stop and mail the CEO; never improvise past a gate.
