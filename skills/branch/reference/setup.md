# 分公司 setup (once per branch office)

Boss-driven bootstrap for running an external dept (e.g. Marketing) as its own session on its own Claude account. Steps 1-3 are the Boss's hands (logins are never the model's to perform); 4-6 the branch session does on first 「分公司上班」.

## 1 · Second account, isolated CLI

- **The invariant, however achieved:** the branch session runs logged into the BRANCH account while the main session keeps the main account, both live at once. The mechanism is the Boss's (e.g. `claude swap` to the branch account, then start the branch session — sessions stay bound to the account they started under); fallbacks: `CLAUDE_CONFIG_DIR=~/.claude-<handle> claude` + `/login`, or a separate macOS user.
- **Verify, don't assume:** `/status` in BOTH sessions must show different accounts — check once after starting the pair, whatever the mechanism.
- Branch session: clock-in plugin available (a swapped account sharing the config dir already has it; a separate config dir needs its own install), model via `/model` (subject to that account's plan).
- Keep both installs on the SAME plugin version — the offices share hooks' on-disk formats.

## 2 · Browser (claude-in-chrome)

- Dedicated Chrome profile for the branch; install the Claude extension there and sign it into the **branch account** (extension roster is account-scoped — the CLI session only sees browsers on its own account).
- The lane's site logins (social accounts, comment platforms) live in that Chrome profile.

## 3 · Mark the dept external

- `.claude/orchestrate.json`: add the handle to `"external": ["<handle>"]` (keep it in `roster` too — the brief file is the branch's identity). From then on the main office's guards treat the lane as external (no in-team spawns, no widget registration, no idle nags for it).
- Optional Obsidian view: point a vault at the repo (or an ancestor) and copy the plugin's `skills/orchestrate/templates/Board.base` into `docs/board/` — table/cards views over the cards; property edits write back to the card files.

## 4 · Worktree + office marker (branch session, first run)

From the repo root, in the branch session:

```bash
git worktree add .claude/worktrees/<handle> -b branch/<handle>
cd .claude/worktrees/<handle>
printf '{"office": "%s"}\n' <handle> > .claude/office.json   # untracked, worktree-local
```

Start future branch sessions IN the worktree. The marker routes the mail nudge to this office; the CEO's checkout has none and stays "CEO".

## 5 · Mail lane

- `docs/board/mail/` in the **MAIN checkout** — shared state (cards · mail · reviews · BACKLOG) is always read/written at the main checkout's paths, from both offices; a worktree's own copy of those files is not the shared surface (the skill resolves `<main>` via `git rev-parse --git-common-dir`).
- Note format: `<YYYYMMDD-HHMM>-<from>-<slug>.md`, frontmatter `from` · `to` · `re: "#NNN"` · `status: unread` · optional `needs_boss: yes`, body free prose. Flip `status: read` after acting.

## 6 · Smoke the lane

1. CEO session: create a card `dept: <handle>` (hand-written note in `docs/board/` with a fresh `#NNN`, `task_id: —`) and a mail note `to: <handle>`.
2. Branch session: end a turn → the 📮 nudge names the mail; claim the card (`status: doing`); reply-mail the CEO.
3. CEO session: end a turn → 📮 nudge for the reply; the board digest shows the card `doing` with the 分 badge on the Boss Board panel.
