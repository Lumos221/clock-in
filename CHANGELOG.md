# Changelog

All notable changes to **clock-in** are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com); this project uses [semantic versioning](https://semver.org)
(`0.x` = pre-1.0, still evolving).

## [0.9.24] — 2026-07-19
### Added
- **The durable project `#NNN` rides every Done record, wearing a coral pill** (Boss's ask: shipped rows showed only the session-scoped platform id — `#29` is unreferenceable tomorrow, `#139` is what she and the CEO actually cite). Completion hook: `card_for` now also returns the heading's own number, and a `#NNN`-headed card ships as `date · #139 · #29 · dept · name · sha` (legacy 5-field lines unchanged, renderer handles both); the BACKLOG task cell gains the same prefix (`#139 INVITE-PDF-REORG — …`), so the durable id survives into both permanent records and is grep-able next session. Renderer: **id pills** — the project `#NNN` in a coral pill (`.pj`), the platform task_id in a neutral one (`.pt`) — on every kanban card head and on the shipped lines' leading ids; inline `#N` references in prose stay plain text. Light + dark verified on a headless-Chrome fixture (both line shapes, done-status card, in-progress card).

## [0.9.23] — 2026-07-19
### Changed
- **Path-disjoint base drift no longer voids an L2 verdict** (Boss's field report, refcheck: the CEO's DECISIONS-log pushes raced dept review windows on the one master line — two reviews bounced in a row with the code never wrong, and the CEO's fix was a full master freeze across every review-to-merge stretch, queueing the Boss's rulings behind review windows). The ancestry rule ("reviewed sha sits on top of current master") is a conservative proxy for the real requirement, reviewed = shipped byte-for-byte; when the drift is **path-disjoint** — master's new commits touch no file of the branch's diff, the normal case since CEO bookkeeping (DECISIONS · board · docs) and dept-owned code are disjoint by the ownership doctrine — that requirement is provable directly: every reviewed file is byte-identical across the mechanical rebase. Doctrine now says so in all three places: **Auditor contract** (drift is judged by paths, pass on the merits + note the drift, NEVER a `.fail` for disjoint drift alone — a drift `.fail` feeds the bounce counter a phantom and can trip the circuit breaker); **SKILL §2.6** (CEO: verdict transfers, rebase + FF in one motion, `git diff --name-only` ∩ empty as the check; bookkeeping never queues behind a review window; freeze master only for overlapping drift, never as the default); **dept SOP** (a disjoint-drift bounce is not yours — flag it, don't rework). Overlapping drift keeps the strict rule: re-review or freeze.

## [0.9.22] — 2026-07-19
### Fixed
- **Collision nudge covers CLI-raised asks** (Boss's screenshot, hours after 0.9.21: CEO-151 "GLANCE round 2" and CEO-152 "FINAL GLANCE", both `#137`, both open). The store detection had WORKED — CEO-152 carried `collides: ["CEO-151"]` — but the 0.9.21 nudge only surfaced collisions collected from the Stop hook's own marker captures, and these asks were raised via `orchestrate-board add` (the tells: kind `discuss`, `batch: null` — markers always stamp `needs`/`info` + a batch id). Two surfaces close it: **CLI `add` prints a `COLLIDES:` warning in its own output** (the raiser is mid-turn, sees it in the Bash result, can close the old ask immediately), and the **Stop hook now reads the flag from the store** instead of the capture, so every add path gets the net; a collider closed in-turn still never fires. The cap moved to a persistent multi-key file (`.claude/collide-nudge-state`) — the 0.9.21 cap shared the single-slot ask-nudge-state with the trailing-ask nudge, which would evict it and re-nudge an ignored collision forever.
### Changed
- **Direction band: format documented** (Boss: "does it have format?"). It always had one — a short leading `LABEL:` renders as the coral head, embedded newlines are preserved, clause-opening circled digits ①…⑳ break onto their own lines, file paths are clickable — but nothing told the CEO, and refcheck's live direction (ad-hoc `S1…S6` enumerators, no newlines) rendered as a wall. The grammar is now in boss-board.md with the anti-pattern named; refcheck's live banner restyled in place (verbatim words, newlines + ① added) and verified on the live board.

## [0.9.21] — 2026-07-18
### Added
- **Boss Board supersede collision nudge** (Boss's field report with screenshot: CEO-143 SIGN and CEO-144 GLANCE — the same #129 sign, one revision apart — both sat open in Needs-you; the explicit-close rule alone has now failed twice, CEO-27/28 before this, so the mechanical layer parked on 07-11 is unparked). `add_entry` detects the **collision**: a new decision ask from the **same dept, same kind, about the same task** as an older still-open one — the task key is the explicit `#task` field, else **the first `#NNN` the TITLE references** (the fallback carried today's case: both asks were raised without the task linkage but led their titles with #129); no key → never flagged. The Stop hook turns the flag into a **one-time block on the raising turn, BEFORE anything supersedes** (the Boss's call — first design auto-resolved silently; she chose the raiser-in-the-loop line: "add it before it supersedes, so the CEO can handle it correctly"): re-end with `@BOSS-DONE[<old-id>]: <one-line outcome>` if the new ask replaces the old (the register closes with a real outcome, not a generic face), or end unchanged and both deliberately stay open. Guards: info and notices never; cross-kind never; **same-turn marker batches never** (one-decision-per-marker lines are separate asks — each capture stamps a batch id); a collider already closed in the same turn never fires; once per collision set. Nothing auto-resolves. Cost: one feedback line + one re-ended turn, only on an actual collision. Doctrine updated in SKILL §4 · dept SOP · boss-board.md; the explicit close stays the rule, the nudge is the net.
### Changed
- **Information column reads newest-first** (Boss's ask). Needs-you keeps its oldest-first queue order (what's waited longest never sinks); Information is a feed, so the freshest fact now sits on top. Verified light+dark on a headless-Chrome fixture (info NEWEST→OLDEST top-down, Needs-you order and counts untouched, History face shows the auto-superseded outcome).

## [0.9.20] — 2026-07-18
### Fixed
- **Task-sync join key: the human card number bridges hand cards to platform ids** (Boss's field report, refcheck: "tasks created by Registrar don't seem to be effectively maintained"). Root cause: the birth hook filled a pre-existing hand-written card only on a byte-exact subject↔name match — refcheck subjects lead with the durable card number (`#130 REDEEM-MODAL-CHROME — …`) while headings read `### #130 · REDEEM-MODAL-CHROME — …`, so the match never landed. Every `task_id` stayed `—`, CREATE appended minimal duplicates (the board's own housekeeping note records retiring "hook-dup #4/#5"), completions retired the duplicate or nothing (shipped rows with dept `—`), and the real card rotted in Active with hand-journaled "DONE" prose. Now the fill matches in three tiers: exact name (historic) → **the `#NNN` the subject leads with** (fills the sole unregistered card headed `### #NNN ·`) → normalised name (separator/space/case drift); ambiguity falls through to an append, never a guess, and a registered card is never re-filled. A completion whose `task_id` matches no card now leaves a trace in `.claude/marker-misses.log` instead of silently retiring nothing. Doctrine (SKILL §2.4 + task-widget.md): a registering subject leads with its card's `#NNN`.
- **Idle-nudge false positive: post-report verification Bash no longer counts as unreported work** (Boss's screenshot, Marketing standing pane: report sent → one `git log` HEAD check → idle → "You are going idle with unreported work" → a wasted rebuttal turn). `bash_readonly()` classifies a command whose every segment is inspection (`git status/log/show/diff/rev-parse/…`, `ls cat head tail grep rg find wc …`, no redirects, git global flags like `-C <path>` skipped properly) as non-work; anything unlisted still counts, and the CEO's manual prompt stays the missed-nudge fallback.
### Changed
- **Idle pings: reconcile trigger, not noise** (Boss's field report: two desks sat idle with dispatch-ready cards until she nudged the CEO herself). The v0 line "Idle ping ≠ done ≠ reported — act only on an explicit SendMessage report" muted every ping globally, discarding the only Boss-free wake-ups the CEO gets; boss-in-pane (0.9.4) was left as a redundant second mute. Inverted: **a ping hands the CEO the turn to reconcile that desk** — report outstanding → ask for it · queued cards → let it pull (`CLAIM`) · queue empty → verify the clean boundary (report filed, `.pass` verified, work merged to the reported sha, card `completed`) then **release the pane or refill it** from dispatch-ready cards. Kept: idle never equals done — merging still needs the report + `.pass`. Boss-in-pane becomes the ONE mute (as designed); the post-pane green light now also verifies the committed sha before release. Dept SOP mirror: idle pings may draw a status ask — answer with the 4-line report. (A turn-end capacity sentinel was considered and parked: with pings live, the event and the attention arrive together; mechanise only if the field shows the CEO still missing it.)
- **Crossed-messages doctrine** (Boss: "it happened a lot of times today in the CEO's pane"). In-flight crossings are inherent to async desks and rise with live-desk count + queue-pull autonomy; the system self-corrects but each crossing cost an unstructured round-trip. Now written down (SKILL §3 + dept SOP): an instruction **names its anchor** (the report sha / message it answers); several messages from one dept arriving together → act on the newest; a dept whose newer facts contradict an instruction **replies with the correction + anchor sha instead of executing** — one correction reply, not a loop. Merges already pin to the reported sha.

## [0.9.19] — 2026-07-18
### Added
- **Board file links open in the default app** (Boss's ask: a `.md` click in the CLI opens the editor; in the panel it dumped plain text into the tab). Split click behaviour: browser-native types (png/jpg/gif/webp/pdf — mockups, marked shots) keep opening in the tab via `/file`; everything else (`.md`, logs, csv, …) now fires the new **`/open` endpoint**, which resolves the path with every `/file` guard (realpath pin under root, linked-worktree fallback, bare-name basename search) and hands the file to the OS default app (`open` / `xdg-open` / `startfile`). Security: `/open` is a side-effect endpoint, so it requires the `X-Board: 1` custom header — a cross-origin page can't send one without a CORS preflight the server never grants, killing drive-by CSRF; verified 403 without the header, 204 on valid paths (full + bare-name), 404 on traversal. The `/file` href stays on every link (right-click/middle-click = raw view); `BOARD_SKIP_LAUNCH=1` exercises routing without launching apps. All suites green.

## [0.9.18] — 2026-07-18
### Changed
- **Boss Board: Information column + structured asks** (Boss's field report, with screenshot). Two problems, one redesign of the ask surface. ① **Information ≠ decisions:** 复盘 verdicts and the CEO-directed 复盘-now flag were crowding Needs-you. The Answered column becomes **Information**: fresh info-kind rows stay visible (blue dot), resolved asks fold behind a **History** sub-header (collapsed by default, count visible, outcome-collapsed faces kept). Routing: new `@BOSS-INFO[<dept>#<id>]: <fact>` marker for any pane's FYI; the Inspector's `@BOSS[Inspector]` verdicts auto-file as info (still unfiltered — the CEO can't touch them); the tally hook's bounce_diagnose flag (CEO action, Boss reads only) files as info, while bounce_escalate and the L1-refute flag (genuine Boss decisions) stay in Needs-you; the header stamp counts only Needs-you. `orchestrate-board add --kind info` for the Boss's own FYIs. ② **Structured asks:** the norm was one bundled essay per marker. New shape `@BOSS[<dept>#<id>]: <one-line ask> :: <detail>` — the title is the row's collapsed face (decidable at a glance), the detail renders in the expansion, and **every file path the ask mentions is extracted into its own clickable files row** under a hairline (dedup'd, same `/file` endpoint). **One decision per marker** — several needs = several marker lines, each its own row; legacy bare asks keep the old behaviour. The essay-ask sentinel now judges the TITLE only (a long detail behind `::` is legitimate) and teaches the new shape. Doctrine updated across department-sop · SKILL §4 · boss-board.md · /board command; store schema untouched (title/body split at render), so existing boards need nothing. Also rides: a prior session's uncommitted direction-band polish (pre-line whitespace + circled-digit ① line breaks + label-checklist head line). Verified: 60 board tests (+3) green; light+dark headless-Chrome renders inspected (Needs-you counts exclude info; verdict + 复盘 flag in Information; structured face shows title only; files row renders).
- **Unmarked trailing asks are now caught mechanically** (Boss's field screenshots: the CEO ended a work burst with "Still open for you: …?" as plain prose — no marker, so the board never saw it and the panel showed nothing waiting while the question died in scrollback). The Stop hook (`stop_boss_board`) now blocks a **lead work turn** (used tools this turn) that ends on a question (`?`/`？` on the final line) with no raise/info marker — once per prompt (state in `.claude/ask-nudge-state`), feedback carries the exact fix; re-ending the turn passes, so a rhetorical or dept-aimed question costs one cheap iteration. Pure conversational turns (锁需求 dialogue, live back-and-forth with the Boss) never trip it by construction — no tool_use, no nudge. Doctrine alongside (SKILL §4 · dept SOP · boss-board.md): **a trailing question IS an ask — prose is transport, the board is the register.** Also: legacy Inspector entries (posted as needs/discuss by pre-0.9.18 stores, like refcheck's live board) now route to the Information column **by dept at render time** — live boards migrate on next poll, no store surgery. Verified: 66 board tests (+6 nudge cases); fixture board with a legacy discuss-kind verdict renders it in Information, Needs-you count unpolluted.
- **Dept work-product authoring standard** (Boss's ask: "how should depts write their files?" — was scattered/partial). New "Work products — naming + structure" section in `department-sop.md` (live-read doctrine → reaches every dept at next spawn, no recruit/restart), pointer from `departments.md`. Naming: **two file classes, no version suffixes ever** — living docs keep ONE stable suffix-free name updated in place (generalises the canon rule; `-v2`/`-final`/date on a living doc is a defect), event docs (reports · sweeps · audits) are `<type>-<subject>-<YYYY-MM-DD>.md`, never edited after the fact. Structure: every long file, and every Boss-facing one, carries a fixed spine with verbatim headings — `TL;DR (≤3 lines)` + `Needs Boss:` up top, then `## 结论` (numbered, one line each, evidence pointers) → `## 依据` → `## 方法` → `## 附录` — conclusion before evidence always (the Boss decides from the top ten lines), stable headings as the grep API, Boss-facing prose rules encoded (one line per paragraph, no em/en dashes, project-relative paths for board linkification), and a file never substitutes for a board ask (the ask's title and the file's TL;DR must agree).
- **Agent frontmatter: inline `#` comments removed everywhere** — field-caught on live reload: the plugin-agent loader read the Registrar's `tools:` comment as tool names (`deliberately`, `minimal`, … registered as tools). All `tools:`/`disallowedTools:` values in `agents/*.md` and `templates/department.md` are now bare lists; the rationale moved to body text/docs. Rule recorded: never put inline comments in agent frontmatter values.
### Fixed
- **Brain regime arms mechanically — the prose switch stopped being the only trigger.** Field case (Boss, twice): after a restart the Fable CEO never read `brain-regime.md` unprompted (the 3-line SKILL switch drowned in the startup wall) and dept spawns went out without the `model:"sonnet"` override, burning opus/roster tiers under a regime that mandates sonnet. Two hooks close it. ① **Session-start regime arm:** SessionStart is the one hook event whose payload carries `model` (optional per docs) — when it says Fable and the project is active, the lead injection now OPENS with one loud line: brain regime applies, read the overlay before planning/dispatching, and binding even before the read — dept spawns carry an EXPLICIT model, no code in the CEO pane. Fires on startup, resume and post-compact (every SessionStart source — exactly the restart moments the miss happened); parity sessions pay zero; model absent → silent, the prose switch stays as fallback. ② **Spawn-tier guard** (extends `pretool_spawn_guard.py`): PreToolUse carries no model field, but the transcript stamps `message.model` on every assistant line (field-verified) — tail-read 64 KB, and a Fable-CEO session blocks any NAMED teammate spawn lacking a `model:` param, with the fix in the feedback. **Only the silent omission is blocked** — any explicit tier passes, because the Boss designates per-dept tiers (field fact, refcheck: Marketing runs at Fable); `brain-regime.md` now records Boss-designated tiers as first-class overrides of the sonnet default. One-shots, parity sessions, Registrar (spawns with `model:"haiku"`) all untouched; both guards fail open. Tests: spawn-guard 16 (+6), session-start 31 (+3), all suites green.

## [0.9.17] — 2026-07-17
### Changed
- **Dept tools: allowlist → `disallowedTools` denylist.** Field cause (Boss): teammates kept lacking tools they needed — audit found the dept allowlist carried two DEAD names (`BashOutput`/`KillBash`, long renamed to `TaskOutput`/`TaskStop`, granting nothing) and omitted `ToolSearch`, which under the allowlist-filters-everything bug locked depts out of the entire deferred registry — every MCP tool included. Root fix instead of a bigger list: the dept template now sets only `disallowedTools: TaskCreate, TaskUpdate, AskUserQuestion, Workflow, PowerShell` — **field-verified (scratchpad probe, 2026-07-17): a denylist filters the deferred registry too** (denied tools are unreachable even via ToolSearch), and everything else flows in with zero rot: MCP tools, `LSP`, `ReportFindings` (the code-review skill's channel), plan-mode tools, worktree tools, `Monitor`, `Artifact` (Boss's call: useful), and any tool the platform adds later. The withheld five: task WRITES stay CEO/Registrar-only (the 0.9.15 design — note `TaskList`/`TaskGet` READS are now deliberately allowed: harmless read-only views, inert while the widget is model-gated, free queue visibility the day it lifts; `CLAIM` remains a dept's only write, via the Registrar) · `AskUserQuestion` (asks go via `@BOSS`; recruit may strike it per-dept on the Boss's word) · `Workflow` (CEO's burst engine) · `PowerShell`. `department-sop.md` teaches the wider surface (ToolSearch before concluding a tool is absent; capability ≠ mandate — owned files and the card still bound what you touch); recruit copies the denylist verbatim, per-dept adjustments only on the Boss's word. Caveat recorded: denylist honouring is probe-proven for subagents; first live 上岗 confirms teammates (worst case is over-granting, which the SOP + L2 gate + Registrar ACL already contain).

## [0.9.16] — 2026-07-17
### Changed
- **One-restart plugin updates — the end of the restart→/recruit→restart sandwich.** Boss's pain: every template-borne release forced a double restart per project because behaviour was distributed by copying. Two structural moves kill the copies. ① **Standing agents go plugin-scope:** 审查官 (Auditor) · 督察 (Inspector) · 书记处 (Registrar) move from `skills/orchestrate/templates/` to the plugin's `agents/` dir (the platform resolves subagent types from plugin scope, teammates included) — they update with the plugin itself, are never copied into a project, and stay out of `roster`. ② **Dept briefs become thin project shells:** `templates/department.md` now carries only identity + project fields (role · 领域标杆 · owned files · Done) plus a FIRST-ACTION pointer — run **`orchestrate-sop`** (new PATH launcher) and follow its output; the whole SOP doctrine (tools discipline · L2 gate · task queue · report format · Boss protocol · CANON rules) moves to `reference/department-sop.md`, read live at every spawn, so **doctrine changes propagate at the next dept spawn with no recruit and no restart at all**. Three inline rules survive in the shell as a fail-safe (plain text is invisible · no ship without L2 · report-and-stop), and a failed `orchestrate-sop` means report-and-wait, never improvise. Migration + drift-safety: two new session-start sentinels (lead-only, fail-open, zero tokens when clean) — legacy `.claude/agents/Auditor|Inspector|Registrar.md` copies **shadow the plugin versions and pin outdated contracts**, so they're flagged for the /recruit upgrade pass (which diffs each for project-local drift, reports it to the Boss, then archives to `.claude/agents/archive/`); and recruit now stamps `briefs_template_hash` (sha256[:12] of the department template) into `orchestrate.json`, so briefs falling behind the shipped template get one nudge line. recruit's activation exception updated (the 督察 ships with the plugin — nothing to author for it). **Field-verified (headless probes, 2026-07-17):** plugin agents register **namespaced** — `clock-in:Auditor` / `clock-in:Inspector` / `clock-in:Registrar` (a fresh session listed them; a spawned `clock-in:Auditor` self-identified as 审查官, so the definition resolves end-to-end) — every spawn-syntax reference now carries the prefix (bare `"Auditor"` won't match), the Registrar's teammate **name** stays bare `Registrar` (what depts message and hooks key on), and the two hooks comparing the transcript's `agentSetting` normalise the namespace (`split(":")[-1]`). Docs-confirmed (plugins-reference · plugins · agent-teams pages): plugin `agents/` is the documented convention; project/user same-named definitions override plugin agents ("the plugin version only takes effect once the originals are removed" — exactly what the shadow sentinel + archive step enforce); teammates from plugin scope are explicitly supported with `tools`/`model` honoured; plugin agents load at session start but **`/reload-plugins` picks up `agents/` + `hooks/` changes mid-session** (SKILL.md files hot-reload on their own). Net effect: routine plugin updates need `/reload-plugins` or at most one restart; the sandwich survives only for genuine shell-schema changes, and the sentinel tells you when.

## [0.9.15] — 2026-07-17
### Changed
- **Registrar promoted to the team's task desk — depts pull their own queue.** Field question (Boss): CEO-only task tools left a dept unable to claim its next card or flip `in_progress` without a CEO round-trip, so finished depts idled through the CEO's desk between cards. Granting depts the tools directly is dead on arrival (big-model teammates are widget-gated per 0.9.x root-causing, and completion must stay the CEO's final call past the L2 `.pass`). Fix: the Registrar — already the gated-CEO proxy — now serves the whole team under a **sender ACL** keyed on the platform-stamped envelope `teammate_id` (names inside message text are never trusted). A dept's only verbs: `CLAIM id=<n>` on a card the CEO pre-`ASSIGN`ed to it (owner = exact handle + status `pending`, verified via TaskGet, then flipped `in_progress` — owner never changes on CLAIM, suffixed respawns don't inherit) plus read-only `LIST`/`GET`; `CREATE`/`ASSIGN`/`STATUS`/`COMPLETE` from a dept come back `REFUSED (CEO-only)`, so **completion stays CEO-only mechanically, not by convention**. CEO side (SKILL §2): queue-ahead dispatch (ASSIGN next cards `pending`, order via `blocked_on`); merge **FF to the sha the report names**, not the branch tip (a queue-pulling dept may already be committing its next card past it); release a teammate only when its queue is empty. Dept side (template): after report, LIST → CLAIM → continue; a CEO send-back outranks a claimed card (park, rework, re-report); 报告即停 clarified — pulling a pre-assigned card is prompted work, not a new leg. The Registrar spawns at first need (widget-gated session or first queued dispatch) and lives until closeout; hooks and the L2 gate are untouched — the sync hooks fire in the Registrar's session and the board keeps mirroring mechanically.
## [0.9.14] — 2026-07-17
### Fixed
- **Board server: zombie reclaim · superseded self-exit · direction band redesign.** Root-causes the "board still shows old code / my direction banner isn't there" trap (field case: refcheck — a 0.9.6 server survived on the derived port for two days). The stale-replace kill used the pidfile pid, which can diverge from the actual port-holder across spawn generations; the kill missed, the respawn drifted to +1, and open tabs stayed orphaned on the zombie. Respawn now reclaims the derived port from any process that *answers as this project's board* (identity-checked via `/state.json` before killing — an innocent squatter is never touched). A server whose on-disk record (version stamp · port) no longer names it now exits within ~30 s **even while polled** — previously an open tab's polling defeated the idle reaper, keeping the stale server immortal while each freshly spawned current one, unpolled, reaped itself. The direction banner became an unboxed masthead band: compass-rose kicker, statement in the panel serif with a leading `LABEL:` auto-styled as the coral head, updated-age at right. Pre-0.9.14 zombies predate the self-exit check — the reclaim path retires them on the next board touch after the plugin updates. Tests: 110 script (+2) + 117 hook, green.

## [0.9.13] — 2026-07-16
### Added
- **Boss Board, four upgrades.** ① **Direction banner** — a standing product-direction section above *On your desk*, set once on the Boss's word (`orchestrate-board direction --text "…"`, `--clear` to remove; one slot, whole-text replace); machine-rendered per poll, zero recurring tokens, hidden when unset, file paths clickable. ② **Outcome-collapsed Answered rows** — `@BOSS-DONE[<id>]: <one-line outcome>` (or `orchestrate-board done <id> --sum "…"`) records the result and the Answered row collapses to it, the full ask one click behind; un-summarised asks keep the old two-line clamp. ③ **Answered column folds by default** — header keeps count + chevron; fold state survives the per-poll re-render. ④ **Today-aware Done cap** — the 5-row cap stretches to keep every today-stamped row; overflow folds into "+N more → BACKLOG.md". Docs updated (boss-board reference · /board command · SKILL marker line). Tests: 108 script + 117 hook, green, verified against a live panel.

## [0.9.12] — 2026-07-16
### Fixed
- **Ambiguity notices no longer feed back into themselves.** An ambiguous `@BOSS-DONE[<dept>]` posted its notice as a plain open board entry, so each notice inflated the next DONE's open-ask count ('2 asks open' begat '3 asks open' listing the first notice) and a dept-level DONE could never resolve again. Notices are now flagged, excluded from resolution counts, capped at one open per dept (a fresh notice supersedes the stale one; an unchanged re-raise dedups), and swept automatically once the dept's queue resolves cleanly. Pre-0.9.12 notices lack the flag — resolve them once by hand (`/board done <id>`).
- **Task chip dedup.** The ask-row task chip rendered hook-born cards as `#14 · #14 · name · status`; `chip()` now carries the same show-each-fact-once guards as the full card renderer. Tests: +4 regressions; 220 total green.

## [0.9.11] — 2026-07-15
### Fixed
- **Stale task ids auto-detach at session start** — platform ids die with their session, and the plugin left the CEO no mechanical home for "this id is dead, re-create at dispatch", so it journaled migration state into card headings (field case, refcheck: panel titles like `#— (session-1 id retired; re-CREATE at dispatch)` — NOT the Registrar's doing, it proxies faithfully). Now the session-start hook detaches any exactly-one-id card whose id is absent from this session's task store (`task_id` → `—`, field surgery only, prose untouched, ambiguous cards left alone), and the existing id-less flag prescribes the re-CREATE. `task-widget.md` adds the rule: never journal id-migration into card names — the `—` field IS that state.

## [0.9.10] — 2026-07-15
### Added
- **New-artefact-dir detector** (Boss's "what if new folders appear later?" — the discovery was write-once, so a dir born after config would accumulate unseen). Every `scan`/`run` now mechanically counts artefact-type files (images/PDF/video) in unconfigured dirs — skipping `.git`/`node_modules`/`archive/`/asset-style dirnames and everything already configured — and prints one `hint:` line when a dir crosses the threshold (8). Detection machine, classification model (only when the hint fires: `/housekeep` judges working-artefacts vs product-assets and proposes the config entry), decision Boss. Recurring runs stay zero-token.

## [0.9.9] — 2026-07-15
### Added
- **Housekeeping: model at the edges, machine in the loop** (Boss's design point). Ad-hoc sweeps: `orchestrate-housekeep run --path <dir-in-project> [--days N]` — the Boss names a folder ("clean up the renders"), `/housekeep` resolves and passes it, no config needed; paths outside the project are rejected. First-run discovery: in a project with no `housekeeping` config and no `docs/mockups`, `/housekeep` now instructs one turn of judgment — find the artefact-accumulating dirs, propose, write the config on the Boss's OK — after which every run and nudge is pure machine again.

## [0.9.8] — 2026-07-15
### Added
- **Timed housekeeping** (`orchestrate-housekeep` + `/housekeep` + a session-start nudge). Field cause: visual working artefacts — the Boss's marked screenshots in, dept-rendered mockups out — are load-bearing while their card is open and clutter after the round ships (~10 MB/day observed in refcheck's `docs/mockups/`). The sweep is **archive-only** (`run` moves stale files to `<dir>/archive/YYYY-MM/`, subfolders preserved; deletion exists only as the explicit Boss-run `prune --days N` over archives) and **reference-safe by construction** (anything named on an Active card, an open Boss-Board ask, `CANON.md` or the SoT never moves, whatever its age — the *Recently shipped* tail deliberately doesn't protect). Dirs configurable via `orchestrate.json` `"housekeeping": [{"path": …, "days": …}]`, defaulting to `docs/mockups` at 14 days when that dir exists. "Timed" the plugin's way: `run` stamps `.claude/housekeep-stamp`, and session start nudges one line when candidates exist and the stamp is a week old — zero tokens when clean. Also sweeps plugin residue (idle-nudge state >7 d, oversized `marker-misses.log` rotated).

## [0.9.7] — 2026-07-15
### Added
- **Spawn-collision guard** (`pretool_spawn_guard.py`, PreToolUse on `Agent`): spawning a teammate whose base handle already has a LIVE member in this session's team is blocked with the fix in the feedback (wait for termination · re-task via SendMessage · or suffix deliberately and void the predecessor). Field case (refcheck, same day the brain regime went live): a released opus dept was respawned at sonnet while 6 minutes into a thinking turn — a shutdown request is processed only at turn end, so the name was still held, `Backend-Engine-2` was minted, and the predecessor kept burning opus on a reassigned task. The guard fires BEFORE the duplicate exists. Only named spawns are judged (one-shots pass); liveness read fail-open from the team config's `members[].isActive`.
- **Lingering-pane sentinel** (session start, lead audience only): live teammates holding no open task are flagged one line each — release or dispatch — with the Registrar, boss-in-pane-marked depts, and suffixed-owner matches exempt. Widget-gated sessions (no platform task store) stay silent rather than guess. Zero tokens when clean, same as every sentinel.
- **Doctrine** (`teammates.md`): replacing a live teammate waits for confirmed termination before reusing the handle; truly can't wait → spawn suffixed deliberately and treat the predecessor's output as void.

## [0.9.6] — 2026-07-15
### Fixed
- **Bare filenames in asks are now clickable on the Boss Board.** Field case (refcheck CEO-102): the CEO wrote the first render with its full path and abbreviated the sibling to its bare name ("docs/mockups/a.png + b.png") — natural prose economy, but the linkifier required a `dir/` segment, so the second file wasn't clickable. Two-ended fix: the page linkifier also matches bare filenames carrying a known artifact extension (png/jpg/gif/webp/pdf/svg/md/txt/csv/json/log/html/yaml/toml — an allowlist so version numbers, dates, domains and `GB/T 7714`-style prose never link), and the `/file` endpoint resolves a bare name by basename search across the main checkout and its linked worktrees (main wins; within a root the newest match wins, since an ask points at the render just produced). Hidden dirs and dependency trees are pruned from the search; every hit still passes the realpath-under-root symlink guard and the viewable-types whitelist.

## [0.9.5] — 2026-07-15
### Added
- **Two-regime orchestration — the brain regime (Fable CEO).** `reference/brain-regime.md` is an on-demand overlay loaded only when the session model is Fable, via a 3-line regime switch under the SKILL CORE RULE — parity sessions (opus CEO, today's rules) pay ~60 always-loaded tokens and never read the overlay; nobody loads both systems. Rationale: the parity CORE RULE ("never dictate method") rested on opus-CEO/opus-head craft parity; a Fable CEO breaks it, so method ownership moves up while the CEO's context goes on a strict diet (Fable is weekly-capped — its context is the org's scarcest resource).
- **Zero-code CEO via differential diagnosis:** the CEO holds words, marked images, tables, 4-line reports and harness artefacts — never code. Bug rounds dispatch a 诊断 table (candidate cause · confirm-by probe · fix-if-confirmed, likelihood-ordered) with two card-borne rules: confirm the cause with probe evidence BEFORE applying its fix, and an escape rung (none verified → report your own diagnosis + evidence, never fix beyond the table). Feature work dispatches interface-level specs + harness. Echo table (mark → understood → planned fix) locks intent with the non-technical Boss before any dispatch; L1 gates the round's batch, not each micro-spec; the CEO judges outcomes from artefacts (L2 stays the independent floor — CEO and spec share blind spots, the gate doesn't).
- **Escalation ladder** (descend only on failure): ① hypothesis dispatch (default, zero code) → ② dept diagnosis (the dept has read the code; CEO sanity-checks a 5-line report) → ③ commissioned read (cheap subagent carrying a sharp discriminating question, conclusions only; direct Read = bounded excerpt when exactness is load-bearing).
- **Org under brain regime:** depts spawn at sonnet via per-spawn `model:"sonnet"` (the override beats the opus pin; one roster serves both regimes, no re-recruit) — with piece-level specs the head's planning job is gone, which also dissolves the opus-head work-hoarding pathology structurally. 审查官/督察 stay opus (verification asymmetry: the top routable tier meaningfully audits Fable designs). Recorded as the one CEO model call in `model-routing.md`; 诊断-card discipline backstop added to the dept template.

## [0.9.4] — 2026-07-15
### Changed
- **SKILL.md deduplicated** (21.2 KB → ~17.8 KB, ~1.2k tokens saved per invocation): each
  rule stated once (peers-never-task · shutdown doctrine · 审查 independence · 报告即停),
  mechanics pushed to the reference files that own them (Registrar spawn → task-widget ·
  L2 bars → the Auditor's contract · activation steps → activate · head/staff two-stage →
  model-routing); old §7 folded into §1, Workers renumbered §8→§7. Two facts re-homed,
  not lost: L1 `.refute`s are hand-archived after resolution (only L2 markers
  self-archive), and `"main"` is the background-subagent channel (→ teammates.md).
- **Teammate lifecycle is per task, not per project.** Field cause: "fresh spawn
  preferred at a clean boundary" + "never shut down mid-project" jointly manufactured
  corpse panes and name-collision duplicates (observed live: `Registrar-2`). Now: spawn
  at dispatch → mid-task always resume → **release at the clean boundary** (completed +
  report received) → the dept's next task respawns fresh on the same handle
  (next-card-same-turn may re-task the live pane). The Registrar is infrastructure
  (lives until closeout). Zombie escape: an externally killed pane can leave a member
  entry blocking its name — shutdown-request it, retry once, only then spawn suffixed.
### Added
- **Boss-in-pane mute + report green light** — `orchestrate-pane start|end|status|clear`
  writes `.claude/boss-in-pane.json` (main checkout, worktree-pierced, gitignored).
  While marked, the CEO treats that dept's pings as pure liveness (reply nothing, call
  nothing, read nothing); on `end`, the dept's unprompted report is the green light to
  release its pane. Dept briefs carry the mirror rule.
- **Idle-nudge hook** (`stop_idle_nudge.py`, riding `stop_dispatch` on Stop + the
  newly registered TeammateIdle): a dept teammate going idle with **unreported work**
  (work tool calls after its last `SendMessage(to:"team-lead")`) gets ONE stderr nudge
  to send its 4-line report. Capped per report-epoch (never loops), suppressed by the
  boss-in-pane marker and by an open `@BOSS[…]` ask, `stop_hook_active`-aware,
  fail-open everywhere; zero tokens on every silent path. Identity is read from the
  teammate transcript stamps (`agentName`/`agentSetting`/`teamName` — field-verified;
  the TeammateIdle input schema is undocumented). The dispatcher now propagates a
  module's block request (exit 2 + stderr) — still one interpreter per turn end.
- **Audience-aware session start:** dept panes now get a slim teammate brief (role line
  naming the agent + settled-question rule + 红线 + SoT) instead of the CEO injection —
  every dept spawn was being told "You are the CEO" and handed the CEO's chore flags;
  the Registrar (mechanical proxy) gets nothing; the lead is unchanged.
### Fixed
- **Registrar round-trip waste:** `task-widget.md` quoted the drive-it grammar loosely
  (`ASSIGN id owner`) while the agent demands strict `key=value` — a real MALFORMED
  bounce in the field; the reference now quotes the exact grammar. `LIST` replies one
  line per task (no descriptions — the CEO wrote them; `GET` for detail); trailing
  "awaiting instructions" filler after replies is banned (invisible to the lead).

## [0.9.3] — 2026-07-15
### Fixed
- **Tombstone cards garbled the panel's Todo column.** Field case (refcheck): during the
  widget-gated era the CEO closed finished cards by striking the heading
  (`### ~~LABEL~~ ALL SHIPPED …`) — the parser split the heading at the first `·`
  (mid-strike), the renderer had no `~~` support, the label chip was escape-only, and
  status-less cards defaulted into Todo. Now a struck/closure-worded heading with no
  status field files as **done** (`TOMB_RE`); `md()` renders `~~strike~~` and strips
  unpaired markers; the label chip renders markdown; hook-born cards drop the redundant
  `#id · #id` chip; `·`-less headings no longer print the same text twice. The
  session-start sentinel now prescribes **delete** (not register-via-TaskCreate) for
  id-less tombstones — the register advice would re-register shipped work, so CEOs
  rightly ignored it and the tombstones rotted.
### Added
- **DECISIONS lookup/impl discipline — template field + token-free sentinels.** Field
  causes (refcheck CEO self-diagnosis): settled questions answered from principles
  instead of the log; rulings "queued" in prose that never became cards (silent loss —
  the dead behaviour re-teaches the dead design); code outliving decisions. Every
  behaviour-changing entry now carries `**Impl:**` — `#<card>` · `parked: <why>` ·
  `none-needed`; a superseding ruling's card must name the removal of the old path.
  Session start flags tagged `[topic-key]` entries with no CANON row and recent (≤7 d)
  entries missing **Impl**, and injects the settled-question rule every session
  (`orchestrate-canon get <topic>` + grep DECISIONS **before** stating what's
  allowed/designed/settled) instead of leaving it to one session's memory. Closeout
  ritual gains a decision-implementation gap audit (every ruling swept against live
  code; each gap becomes a card or an explicit park).
- **Clickable file paths on the panel.** Asks and cards constantly carry artifact paths
  (render mockups, review files) that the Boss had to hunt down by hand. Project-relative
  paths with an extension now render as links onto a new daemon endpoint `/file?p=…`;
  images/PDF display inline, everything else ships as `text/plain` (never an executable
  type — html/svg could script in the board's origin). Guards: relative paths only,
  realpath pinned under the checkout (kills `..`/symlink escapes). A miss in the main
  checkout falls through to the repo's **linked worktrees** — pre-merge renders (the
  exact "your eyeball before L2/merge" case) live only in a dept pane's worktree; the
  main checkout wins when both have the file. URLs are never mistaken for paths; a link
  click doesn't toggle its row.
- **Needs-you readability for essay asks.** Field case (refcheck CEO-89, 800+ chars):
  boss-board.md's decidable-ask rule (question · options · recommendation, 1–2 lines)
  is prose, and prose rots. Panel side: an expanded ask now breaks at clause
  enumerators (①…⑳ — inline references like "chain ①②③④" stay intact) and gets
  looser leading + a gap before the meta line. Root-cause side: a session-start
  sentinel flags open asks over 280 chars (id + size) with the re-raise prescription
  (`@BOSS-DONE[<old-id>]` + decidable one-liner, detail → file/card).

## [0.9.2] — 2026-07-14
### Fixed
- **Registrar reported the widget missing — its own `tools:` allowlist was starving it.**
  First real-use spawn (refcheck) found no task tools on haiku, where they demonstrably exist.
  Root cause (probe-verified + transcript-verified): a teammate's allowlist filters its ENTIRE
  tool surface, including ToolSearch and the deferred registry — the platform docs' "task tools
  are always available to a teammate even when `tools` restricts other tools" does not hold
  under deferred tool loading. A sibling probe with a restricted list lost ToolSearch and even
  SendMessage (its report was composed but never delivered). The template now names
  TaskCreate/TaskUpdate/TaskList/TaskGet explicitly, and the spawn step **verifies by doing**
  (call TaskList once) instead of trusting a ToolSearch miss — robust whether the tools arrive
  direct or deferred. Fix in a live project: re-copy the template over
  `.claude/agents/Registrar.md`, restart the CEO pane (agent files load at session start),
  respawn the Registrar.

## [0.9.1] — 2026-07-14
### Added
- **书记处 Registrar — the task widget for widget-gated sessions.** Field finding: the platform
  currently withholds TaskCreate/TaskUpdate/TaskList/TaskGet from interactive sessions on the
  big models (Sonnet 5 / Fable 5 / Opus 4.8) while Haiku 4.5 sessions keep them — and a **haiku
  teammate of a gated lead gets the full widget** (verified live: ToolSearch load, TaskList,
  TaskCreate onto the shared team list). New standing file `templates/registrar.md`: a minimal
  haiku teammate that proxies the CEO's literal lifecycle commands (`CREATE`/`ASSIGN`/`STATUS`/
  `COMPLETE`/`LIST`/`GET`), relays failures verbatim (a gate-blocked COMPLETE included — the L2
  gate keeps enforcing through the proxy), and the 0.9.0 sync hooks fire in its session, so the
  board stays machine-fresh. CEO spawns it only when its own ToolSearch finds no task tools
  (session-start flag + SKILL §2.4 route there); recruit installs it as the third standing file.
  Availability matrix + protocol: `reference/task-widget.md`.

## [0.9.0] — 2026-07-14
### Added
- **TaskBoard.md now follows the platform task widget** (field report: "TaskBoard.md constantly
  got stale, and tasks are messier without taskwidget created"). The widget is system-level —
  its schemas ship in the harness and task state is re-injected as reminders — so it is the
  channel that actually gets followed; the markdown stays the durable, git-diffable, hook-readable
  layer. New `posttool_task_sync.py` (PostToolUse on `TaskCreate|TaskUpdate`): `TaskCreate`
  **births the card** with `task_id` pre-filled (a hand-written card with a matching name is
  filled, not duplicated; a stale card holding a recycled id is detached with a trace in
  `marker-misses.log`); `TaskUpdate` mirrors `pending→todo` / `in_progress→doing` and fills an
  empty `dept` from `owner` (the CLI's `TaskCreate` takes no owner — assignment happens at
  dispatch via `TaskUpdate`, verified against the 2.1.206 binary); a `deleted`/`cancelled`
  task retires its card (forward-proofing — the current status enum ends at `completed`). The completion hook
  now also **deletes the card** on `completed` (was a manual CEO step — the top staleness source).
  All card surgery keys on a `task_id` field that is exactly one id — shared multi-id cards and
  prose the hook only half-understands are never touched. Session start flags Active cards that
  carry no `task_id`. CEO contract updated in `SKILL.md` §2.4/§2.6/§2.7 + the TaskBoard template;
  dept flow unchanged (depts still own their card's fine states — `review`/`blocked` stay prose).

### Added (bloat sentinel)
- **Token-free file-discipline sentinel at session start.** One-off housekeeping doesn't hold:
  prose caps (SoT ~15 lines · cards are pointers) rot silently between cleanups. The
  session-start hook now re-measures every session and flags violations — SoT over ~20
  non-empty lines / 2k chars, any Active card block over ~1.2k chars (named), plus the
  existing unregistered-cards flag. Detection only, zero tokens when clean, one line per
  violation until fixed; the hook never truncates CEO prose. Dept brief gains the matching
  rule: card `status` is ONE line, history goes to reports/DECISIONS. New
  `hooks/test_session_start.py` (5 tests).

### Changed
- **Orchestrate spine diet** (field report: sessions loaded 80k+ before real work; the skill's
  wholesale-loaded SKILL.md was ~28.4k chars). Progressive disclosure pass: activation/adoption
  + closeout ritual → `reference/activate.md`, task-widget contract + sync-hook behaviour →
  `reference/task-widget.md`, spawn syntax/lifecycle/experts/Workflow/model-routing detail →
  `reference/teammates.md`, morning-brief command → `reference/meetings.md` (it already held the
  field shapes). SKILL.md lands at ~20.9k chars (−26%, ≈2.5k tokens per invoke) with **every rule
  and every section number kept** — external references (§2.3/§2.6 from recruit, §4 from
  meetings, "Files") stay valid; only procedural detail moved behind pointers.

### Fixed
- **`canon.py set` silently registered garbage on positional args** (field report 2026-07-11:
  a hand-registration of `faq-content` produced an empty-topic row and printed "created").
  The CLI is flags-only; positional calls matched no flag and fell through to empty defaults.
  `set` now refuses loudly (usage + exit 2) when `--topic`/`--file` are missing; `board.py add`
  had the same foot-gun (empty card under the default dept) and gets the same guard. Regression
  tests reproduce the exact reported call shape.

### Changed
- **Supersede rule for Boss-Board asks.** Field case: an answered ask re-raised in revised form
  left BOTH open in Needs-you (`CEO-27`/`CEO-28`) — and two opens make a bare dept-level DONE
  ambiguous. The marker contract now says it in all three places a pane reads (`department.md`
  template, `SKILL.md` §4, `reference/boss-board.md`): re-raising a revised ask → `@BOSS-DONE[<old-id>]`
  in the same turn; the board never auto-supersedes. Rule only for now — a mechanical
  same-task supersede backstop is parked.
- **README rewritten** around a functions-first structure (what it does, no mechanism talk);
  em-dashes stripped from rendered prose; stale `⚠ Needs you` reference cleaned from
  `reference/boss-board.md`.

## [0.8.0] — 2026-07-10
### Changed
- **Needs-you becomes a GitHub-issues-style list.** Stacked paragraph cards → one contained
  list of one-line rows: state dot (red needs · blue discuss · grey parked), the ask clamped
  to a single line, an `id · dept · kind · task #` meta line, right-aligned waiting-age, hover
  highlight, click to expand the full ask + task chips. Chosen over a Notion-style table
  because free-length ask text has no sane column width; the issue-row pattern keeps the same
  scannability with graceful expansion.
- **Letterhead header.** The page opens with the **project name** (the root folder of the
  session) as the masthead under a small BOSS BOARD eyebrow, live status beneath, over a
  hairline rule; the browser title follows (`<project> · Boss Board`). "Needs you" becomes a
  section header like the others.
- **Design pass for the README hero — Anthropic theme** (Boss-pinned): ivory `#F0EEE6` page,
  warm paper surfaces, Claude-coral eyebrow/accents, serif masthead, warm-tuned state colours,
  matching Claude-dark mode; monospace ids/ages/counts (the ops-console register); keyboard
  focus + Enter-to-expand on every card.
- **Releases decouple from deploys.** The daemon/tab staleness key is now `version + content
  hash of board.py`, so a code edit self-deploys (server replaced, tabs hot-reload) without a
  version bump — no more per-edit release churn.

## [0.7.9] — 2026-07-10
### Fixed
- **Expanded cards no longer collapse under you.** The panel rebuilt the whole DOM on every
  ~1.5s poll, wiping a just-clicked expansion. It now skips the re-render entirely when the
  data hasn't changed, remembers which cards are expanded across real re-renders, and a click
  that's selecting text no longer toggles the card.

## [0.7.8] — 2026-07-10
### Changed
- **Done column caps at the 6 most recent entries** (+N-more pointer to BACKLOG.md) — it's a
  glance at momentum, not the archive; legacy boards with 20+ lingering done cards no longer
  pile up there.

## [0.7.7] — 2026-07-10
### Fixed
- **Shipped entries become real cards.** The *Recently shipped* lines in the Done column were
  bare text runs on the tinted column — next to proper cards they read as a broken list. They
  now carry the same card chrome (surface, border, radius), and the line-clamp moved to an
  inner box so no sliver of the cropped 3rd line bleeds into the padding.

## [0.7.6] — 2026-07-10
### Changed
- **Ask cards join the kanban's design system.** They were full-size paragraphs on heavy colour
  slabs next to the tight GitHub-style task cards — now: same compact type scale and radius,
  washes pulled back to faint tints (state still reads via left border + tint), and ask bodies
  clamp to 4 lines with click-to-expand, so the two halves of the panel finally look like one
  page and an essay-length ask can't dominate the queue.

## [0.7.5] — 2026-07-10
### Changed
- **Readability pass on the panel (ADHD-friendly).** Asks cap at a ~78ch reading line (full-width
  cards were ~180ch); the queue sorts **oldest-first** with a "waiting 4h" age chip per card, so
  what's waited longest never sinks; every state gets a coloured undershade — needs = red wash,
  discuss = blue, columns tinted green/amber/violet, blocked cards red, review cards purple;
  *Recently shipped* lines render markdown, clamp to 2 lines and expand on click (they were an
  unrendered wall of paragraphs); a leading `** ` (pane bullet convention, not bold) no longer
  bleeds bold across the whole ask. PAGE is a raw string now (kills the `\*` SyntaxWarning).

## [0.7.4] — 2026-07-10
### Fixed
- **Panel readability.** `**bold**` and `` `code` `` in asks and cards now render (minimal
  markdown applied AFTER escaping — the XSS guarantee holds); long card bodies clamp to a few
  lines and expand on click, so a wall-of-text card no longer swallows the column.

## [0.7.3] — 2026-07-10
### Fixed
- **The panel daemon now survives plugin updates by replacing itself — not by serving the old
  board forever.** The server is a detached long-lived process holding its page in memory; after
  an update every hook found it alive and politely reused it, so the Boss kept seeing the
  pre-update panel no matter how many sessions restarted (field case: two 25-hour-old daemons
  still serving the pre-kanban board). The spawn now stamps the plugin version into the runtime
  dir; `ensure_server` kills-and-respawns a live-but-stale server, and `/state.json` carries the
  version so an open tab **hot-reloads itself** the moment a newer server answers. One-time cost:
  tabs opened before 0.7.3 must be closed by hand once.
- **Kanban parser hardened against real boards.** Field data (refcheck) broke three template
  assumptions: *Recently shipped* can sit ABOVE *Active* (the positional split returned 0 tasks),
  status lines are prose ("doing — L1 PASS 3rd round…", "✅ DONE + L2-passed" — first status
  keyword now wins), and the shipped fallback swept every bullet in the file into the Done column
  (now bounded to its own section; parked sections excluded).

## [0.7.2] — 2026-07-10
### Fixed
- **Alias detector false-positive on legitimate non-roster workers — caught in the field.**
  Projects run workers outside `roster` (on-demand depts, experts under a project-local key);
  a legitimate bounce from one would have flagged its canonical handle as an alias. The
  detector now arms with **roster ∪ `.claude/agents/` filenames** — the design-native registry
  of every legitimate handle (each spawnable worker has an agent file) — instead of adopting
  any project-local config key.

## [0.7.1] — 2026-07-10
### Fixed
- **Legacy-alias evasion of the circuit breaker — caught in the field.** A downstream project's
  Auditor.md carried a Boss-signed local rule ("`<dept>` must be the canonical roster handle" —
  born from a real `web.40.1.fail` incident); `/recruit`'s verbatim standing-file overwrite
  silently dropped it, re-opening the hole: `web.40.1.fail` + `Frontend.40.2.fail` on the same
  task are two buckets of one — neither trips `bounce_diagnose`. Three-layer fix:
  - the normalization rule now lives **in the plugin's `auditor.md` template** (project-independent
    wording), so every project gets it and no local fork is needed;
  - the tally hook grew an **alias detector**: any `.fail` prefix not in orchestrate.json's
    `roster` raises a Boss-Board flag naming the alias — protection no longer depends on an
    agent obeying prose;
  - `/recruit`'s upgrade pass now **diffs before overwriting** a standing file: project-local
    drift (e.g. a signed amendment) is reported to the Boss — folded upstream or relocated —
    never silently dropped. (That silent drop is exactly what happened.)

## [0.7.0] — 2026-07-10
### Added
- **Boss Board v2 — a decision panel, not an ask list.** The Boss's complaint: items said
  "needs you" but never carried enough context to decide. Three fixes, one page:
  - **Asks link to their task.** New marker grammar `@BOSS[<dept>#<task_id>]: <ask>` (old bare
    form stays valid; `@BOSS-DONE[<dept>#…]` tolerated). A linked ask renders with its task card
    as a chip (label · #id · name · status); an unlinked ask falls back to the dept's in-flight
    cards. `orchestrate-board add` gains `--task`.
  - **Current-iteration kanban under the asks.** The panel now renders `TaskBoard.md` live
    (re-read per poll): Todo (+blocked, badged with `blocked_on`) · In progress (doing + review) ·
    Done (done cards + the hook-maintained *Recently shipped* tail) — GitHub-Projects style, with
    counts, so the Boss can locate the task that needs them and glance at the related ones.
  - **Asks must be decidable from the board.** Dept brief now requires: question · options ·
    recommendation + why, 1–2 lines — a bare "need your input" ping is the anti-pattern.

## [0.6.1] — 2026-07-10
### Changed
- **The artifact model slims to two hand-curated surfaces.** Nine docs artifacts existed, four
  hand-maintained, three overlapping. Now the CEO curates exactly two — a hard-capped `SoT.md`
  and TaskBoard *cards* — everything else is machine- or event-written:
  - **`SoT.md` = the project's CLAUDE.md** (Boss's framing): a lean curated index — Goal ·
    Now (three one-line slots: live/blocked/next) · fixed + curated pointers. **Hard cap ~15
    lines** — it's hook-injected into every session, so bloat was a recurring token tax. The
    hand-written "Decisions" section is gone: it predated CANON, whose machine-maintained
    key-decisions mirror now does that gathering (SoT keeps one pointer).
  - **TaskBoard's *Recently shipped* is hook-maintained.** The completion hook (which already
    writes the BACKLOG row) now also inserts the shipped one-liner between
    `<!-- SHIPPED:START/END -->` markers, newest first, trimmed to ~5 — the CEO just deletes
    the finished card, no hand-copying between files. Boards without the markers are left alone.
  - **`复盘-<dept>.md` merged into one `docs/复盘.md`** (dept moves into the row) — fewer
    files, same one-line records; the 督察 greps its dept.
  - CANON/DECISIONS deliberately untouched (machine registry vs why-log — the load-bearing
    pair), BACKLOG/reviews are free (machine-written, never loaded).
- `/recruit`'s upgrade pass now also migrates docs: adds the SHIPPED markers to an existing
  TaskBoard, merges per-dept 复盘 files, and flags (never rewrites) an over-cap SoT.

## [0.6.0] — 2026-07-10
### Changed
- **The HR discipline ladder is gone; a per-task circuit breaker replaces it.** The
  retune→fire ladder copied how companies manage *people* — but replacing an agent is a cheap
  respawn, consecutive bounces on one task share one root cause, and "dept identity" was only ever
  a filename prefix. L2 封驳 are now counted **per task** (`<dept>.<id>.<n>.fail` — the id was in
  the ledger all along): `bounce_diagnose` (default **2**) halts the rework loop for a one-shot
  复盘; `bounce_escalate` (default **3**) puts the stuck task on the Boss Board. The 复盘 keeps the
  old attribution menu (① dept prompt → rewrite + respawn · ② CEO brief → rewrite the card ·
  ③ task too hard → re-scope/split/bump tier) and still appends the 复盘 log; the cross-task signal
  is now *same root cause twice* in that log (→ roster audit), not raw bounce totals.
- **人事部 (HR teammate) → 督察 (Inspector), a standing-file one-shot subagent** — the 审查官
  pattern (`templates/inspector.md` → `.claude/agents/Inspector.md`, never in `roster`, no pane,
  no teammate slot). Every job it has is a bounded single-context judgment (diagnose one task,
  author one agent file, one audit), its memory is the on-disk 复盘 log, and independence comes
  from fresh instances + `@BOSS[Inspector]` markers landing on the Boss Board unfiltered — not
  from a standing pane. 审查官 gates the *work*; 督察 inspects the *org*. (`templates/hr.md` and
  `reference/hr-oversight.md` removed → `templates/inspector.md`, `reference/inspector.md`.)
- **No counter resets, ever.** The old design reset counts by archiving files (a case-sensitive
  `mv` SOP that contradicted the tally's flag-once sentinels and its `retune+3` fire arithmetic —
  after one full cycle a dept could fail forever unflagged). Now: counts are per task and expire
  with it (completion archives that task's `.fail`s + sentinels alongside its `.pass`), and a
  sentinel whose count drops below threshold re-arms itself. Thresholds simplified:
  `bounce_diagnose`/`bounce_escalate` replace `retune_after_bounces`/`fire_after_more_fails`;
  the unused `chaos_depts_near_fire`/`chaos_idle_rounds`/`chaos_redline_hits`/`chaos_pingpong`
  knobs are dropped (`chaos_ceo_refutes`, `chaos_unowned_domain_fails`, `meeting_batch` stay).
- The 审查官's L2 contract now tells the bounced 部门, from the 2nd `.fail` on one task, to stop
  reworking and report blocked for a 复盘 — the circuit breaker is in-band, not just on the board.
### Added
- **Roster upgrade path.** `/recruit` in a project that already has a roster now reconciles it to
  the current templates: re-copies Auditor/Inspector verbatim, regenerates dept files (carrying
  only the project-specific fields), archives a pre-0.6.0 `HR.md` + drops it from `roster`, and
  reconciles threshold keys — so an existing project adopts a new plugin version by running
  `/recruit` once and restarting.

## [0.5.2] — 2026-07-10
### Fixed
- **Review-gate bypass via stale 审查-passes.** Platform task ids are small integers that restart
  with each session, while `docs/reviews/` persists — a new session's task `3` could be marked
  `completed` against LAST session's `3.pass`, with no review ever happening. Completion now
  retires the pass (`posttool_backlog_log.py` archives it to `docs/reviews/archive/`), and closeout
  (SKILL §2.7) archives passed-but-never-completed strays.
- **Worktree piercing applied everywhere, not just half the hooks.** 56a921c fixed
  `stop_boss_board.py`; but `stop_canon.py`, `stop_refute_tally.py`, `canon.py`'s own
  `project_root` (every `orchestrate-canon` call a dept makes from its worktree),
  `posttool_backlog_log.py` and `session_start.py` still resolved to a worktree's private root —
  registering CANON rows / tallying ledgers / appending BACKLOG into copies that vanish on reap.
  All now pierce to the main checkout via the same `board.main_checkout`.
- **Accident-guard blind spots.** Patterns were case-sensitive, so `DROP TABLE` (SQL is
  conventionally uppercase) and `rm -Rf` never matched; `git push -f` (the short flag) wasn't
  covered; `rm -r -f` / `--recursive --force` (separate/long flags) weren't either. rm detection
  is now a real flag parser; everything else matches case-insensitively. New test suite
  (`hooks/test_accident_guard.py`).
- **Boss Board HTML injection.** The panel escaped only `text`; `id`/`dept`/`kind` were
  interpolated raw into `innerHTML`, and the `@BOSS[<dept>]` grammar happily accepts
  `<img/src=x/onerror=…>` (no whitespace needed). All fields now escape, quotes included.
- **Stale-marker replay.** The stop hooks walked backwards past a text-less final assistant
  message and re-applied markers from an EARLIER turn — e.g. re-raising a @BOSS ask the Boss had
  already resolved. Only the last assistant message is read now (`hooks/hooklib.py`).
- **Widened `affects` silently dropped.** Re-registering an unchanged canonical answer with new
  dependant depts returned `unchanged` before touching `affects`; the new depts were never
  flagged. They now get the same first-read flag they'd have received at creation.
- **Ambiguous `@BOSS-DONE[<dept>]` swallowed.** With ≥2 open asks the hook resolved nothing and
  said nothing — the dept believed it resolved while its asks stayed open forever. The ambiguity
  now lands on the board as a discuss item naming the open ids.
- **`session_start.py` armed only from the project root** (exact-cwd check); it now walks up and
  pierces worktrees like every other hook, so a session started in a subdirectory still arms.
- **TaskBoard template contradicted the L2 flow** ("the 审查官 marks done" — a pre-0.5.0
  leftover); it now matches SKILL §2.6 / auditor.md: the CEO marks done on an L2 pass.
- **Canon archive clobbering.** `archive_file` used a bare `os.replace` — archiving a second
  same-named file destroyed the first archive. Collisions now get a timestamp suffix (same for
  retired passes).
### Added
- **`tools:` pinned in every agent template.** Dept heads (department.md) get work tools but NO
  task-lifecycle tools — with its own L2 pass in hand a dept could otherwise `TaskUpdate→completed`
  itself past the gate, voiding "the CEO owns the lifecycle". The 审查官 gets judge-only tools
  (no Edit — it never fixes); experts get read-and-research only.
- **Marker-miss log.** The marker channel is fail-open end to end, so a malformed `@BOSS`/`@CANON`
  line used to vanish without a trace; such lines now append to `.claude/marker-misses.log`.
- **`@CANON` tolerates trailing sentence punctuation** — a full stop at the end of the marker line
  used to void the registration silently.
### Changed
- **One Stop dispatcher instead of three processes.** `stop_dispatch.py` runs the three stop hooks
  in-process (stdin parsed once, transcript read once, each isolated by its own try) — every turn
  end used to pay three interpreter start-ups. Shared hook plumbing now lives in `hooks/hooklib.py`.
- **Server spawn race closed.** `ensure_server`'s check+spawn window now runs under the store lock —
  two hooks on the same Stop event could double-spawn the panel server and drift the port.
- Removed the dead `refute_rounds` threshold from `templates/orchestrate.json` (`chaos_ceo_refutes`
  is the knob the tally actually reads); SKILL now says worktrees cut from the **default branch**,
  not literal `master`; activation gitignores the board's runtime state.

## [0.5.1] — 2026-07-07
### Fixed
- **Boss Board lost-update race.** `scripts/board.py`'s store was a plain read-JSON → modify →
  write-JSON with no locking, and two Stop hooks (`stop_boss_board.py`, `stop_refute_tally.py`) can
  both react to the same turn and both write to it. Whichever finished saving last silently
  overwrote the other's just-added entry — no error, nothing in any log, because both hooks are
  fail-open by design. A `@BOSS[CEO]` ask could vanish between the model saying "Board updated" and
  the panel actually showing it. Added `_StoreLock`, a stdlib-only cross-process lock (`os.O_CREAT |
  os.O_EXCL`, atomic on POSIX and Windows) around every write path (`board_add`/`board_done`/
  `board_resolve_dept`/`board_park`/`board_reopen`); fails open past a 2s wait and reaps a lock
  abandoned by a crashed hook after 5s, so it still can't hang a turn. Regression tests spawn two
  real OS processes racing on the same store to prove entries from both survive.
- **人事部 re-flagging a dept the Boss already resolved.** `stop_refute_tally.py` grouped `.fail`
  ledger files by the literal, case-sensitive filename prefix (`Frontend.8.1.fail` vs
  `frontend.8.1.fail` counted as two different depts). A dept's bounces could fragment across
  casing variants, each crossing the retune threshold on its own sentinel — so renaming or
  re-casing a review file could re-raise "the same" HR alert after the Boss had already resolved
  it (and, in the other direction, could silently under-count a dept that never accumulates 3 in
  any single casing bucket). Dept keys are now lower-cased before counting and before building the
  sentinel filename; display text keeps whichever casing was actually seen.

## [0.5.0] — 2026-07-05
### Added
- **Token-saving two-stage execution.** A 部门 now runs its **head** (the teammate/pane) on **opus**
  — plan + precise per-piece specs + review — and delegates the *typing* to cheap **staff** (one-shot
  subagents it spawns; `sonnet` default, `haiku` **only when a deterministic script could do the
  piece** — and a bounced `haiku` piece is redone on `sonnet`, never retried). Most output tokens move
  to cheap tiers while opus stays the thin planning/review layer. Smart model plans, cheap model
  implements.
- **`hooks/stop_refute_tally.py`** — auto-tallies the 审查 ledger (`docs/reviews/*.refute` / `*.fail`)
  each turn and raises **one** Boss-Board item when a documented `orchestrate.json` threshold is first
  crossed (flag-once via a sentinel). `orchestrate.json` stays thresholds-only; the marker files stay
  the ledger — no counter to drift.
- Hook tests: `hooks/test_review_gate.py` (incl. a worktree-shadow case) · `hooks/test_refute_tally.py`.
### Changed
- **`reference/model-routing.md` rewritten** (SSOT): the head/staff split; the only per-spawn model
  decision is a head choosing each staff spawn's tier; standing roles (部门 heads · 审查官 · experts)
  are opus, pinned in frontmatter; a dated, refreshable model menu (alias-first, so a stale price never
  breaks routing); `fable` documented as **non-routable** (a Boss hand-switch only).
- **Corrected L2 flow.** The **部门 invokes the 审查官 itself**; a FAIL bounces straight back to the
  dept (CEO uninvolved); a PASS goes up, and the **CEO** makes the final merge call and owns
  `TaskUpdate`. The Auditor now writes only the review marker + verdict — it never mutates task state.
  Fixes a subagent-completes-the-CEO's-task bug and the duplicated report/ping. `SKILL.md`
  §2.5/§2.6/§8 · `templates/auditor.md` · `templates/department.md`.
- **CEO orchestrates only** — removed the "CEO may *suggest* a method" carve-out from `SKILL.md`
  §0/§7 and `department.md`; craft is wholly dept-owned (the CEO and every dept head are both opus, so
  there's no craft asymmetry to justify it).
- `templates/department.md` frontmatter now pins `model: opus`.
### Fixed
- **Review-marker anchor is worktree-invariant.** `hooks/pretool_review_gate.py` and the 审查官 resolve
  the project root via `git rev-parse --git-common-dir` → its parent (the main worktree), so a `.pass`
  written from a linked worktree under `.claude/worktrees/` lands where the completion-gate hook (in
  the main tree) looks. Previously the marker could be written where the check never found it —
  silently blocking completion — the moment `orchestrate.json` became git-tracked. Falls back to the
  ancestor walk for non-git projects.

## [0.4.2] — 2026-07-02
### Changed
- **Spawn-kind hard rules on both sides of the org** (from a live incident: a dept passed
  `name:` when spawning its research staff, creating *orphaned* pane-agents — live,
  unmanaged, on nobody's roster). Dept briefs (`templates/department.md`) now prohibit
  `name:` outright — staff/experts are one-shot; `SKILL.md` §8 requires `name:<handle>`
  on every 部门 spawn and bans `name:` on one-shots (staff · expert · 审查官 · research).
### Fixed
- §8's orphan description claimed a non-lead's named spawn gets "no pane" — orphans can
  open panes; they're unmanaged, not invisible.

## [0.4.1] — 2026-07-02
### Changed
- **`reference/model-routing.md`** is now the single source of truth for per-role model
  routing; `SKILL.md` / `departments.md` / the templates point at it instead of restating
  the policy.
- **Lean pass** over `SKILL.md`, `departments.md`, the dept/HR templates, and the plugin
  description — rules stated once (no-relay, ≤6 concurrent, non-overlapping files, own-domain
  bar, bounce counting), L1/L2 bar definitions and marker mechanics deferred to the 审查官
  contract, `plugin.json` description cut to one line.
### Fixed
- **`orchestrate` now actually registers as a skill.** Its frontmatter `description`
  spanned multiple raw lines — invalid YAML, so the skill (and its 「开始上班」 trigger)
  was silently absent from the skill registry in every prior version. Folded to a
  single line.
- **Boss Board opens the panel once**, on server start — later asks refresh the
  already-open window instead of popping a duplicate (explicit `/board` still opens on demand).

## [0.4.0] — 2026-07-01
### Added
- **CANON now indexes key in-force _decisions_, not just files.** A registry row can
  point at a `DECISIONS.md` entry (pointer = the literal `DECISIONS`), resolved by
  grepping the **topmost** `[topic-key]` tag — no line numbers, no fragile `#anchors`.
- The decision entry's headline is **mirrored** into `CANON.md` as the gist (authored
  once in `DECISIONS.md`, so it can't drift). Register/supersede with
  `@CANON[<dept>] <topic> → DECISIONS (affects: …)`.
- `DECISIONS.md` `[topic-key]` tag convention; `orchestrate-canon get <topic>` prints
  the mirrored headline + the log pointer.
### Changed
- `SoT.md`'s hand-maintained **"Key decisions"** section folds into CANON (now a single
  read-first index of files **and** decisions).

## [0.3.0] — 2026-07-01
### Added
- **Canonical Answers registry** — machine-maintained `docs/CANON.md`, the read-first
  index of the current canonical **file** per answered question. `orchestrate-canon` CLI
  (`set`/`get`/`list`/`ack`/`supersede`/`archive`) + `bin` launcher.
- `@CANON[<dept>] <topic> → <path>` / `@CANON-ACK` markers captured by a fail-open
  `Stop`/`SubagentStop` hook — registered from the dept's own message, so the pointer
  can't be lost in a CEO relay.
- Cross-domain handoff (`affects → needs-recheck → ack`) and a stable-name +
  archive-on-supersede file convention.
### Changed
- `SoT.md`'s hand-maintained "Canonical files" section replaced by a pointer to CANON.

## [0.2.0] — 2026-06-30
### Added
- **Boss Board** — a live "Needs-You" panel aggregating every pending ask for the Boss
  across panes. `/board` command + `orchestrate-board` CLI + a singleton localhost,
  self-refreshing panel (Python stdlib only, idle self-reap).
- `@BOSS[<dept>]:` / `@BOSS-DONE` markers captured by a `Stop`/`SubagentStop` hook;
  idempotent add (anti-spam), dept-prefixed ids, targeted reads.

## [0.1.0] — 2026-06-23
### Added
- Initial founder-mode orchestration: a multi-department Agent-Teams squad (CEO ·
  departments · 董事会) running the `规划→审查→派发→执行→产出审查→汇总→报告` spine, a hard
  **2-layer 审查 gate**, the **红线** (law-offense) boundary owned by 法务部, and
  independent **人事部** oversight.
- Skills: `orchestrate` + `recruit`. Hooks: review-gate, accident-guard, backlog-log,
  session-start. Rendered morning brief (`orchestrate-brief`). Artifact model:
  `SoT.md` · `TaskBoard.md` · `BACKLOG.md` · `DECISIONS.md`.

[0.4.2]: https://github.com/Lumos221/clock-in/releases/tag/v0.4.2
[0.4.1]: https://github.com/Lumos221/clock-in/releases/tag/v0.4.1
[0.4.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.4.0
[0.3.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.3.0
[0.2.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.2.0
[0.1.0]: https://github.com/Lumos221/clock-in/releases/tag/v0.1.0
