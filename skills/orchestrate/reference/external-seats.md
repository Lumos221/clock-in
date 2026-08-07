# External terminal seats

> On-demand reference for the CEO. An external terminal seat = an agent running on
> another terminal (Codex CLI, etc.), bound to an existing 部门, working through the
> file protocol in `docs/board/`. **Company structure stays untouched: a card's
> `dept` is always the 部门; the seat is only the executing terminal.** Codex-side
> knowledge lives in the project's AGENTS.md, not here.
>
> **命令来源**：dispatch/mail/work/term 都是 **agent-bridge 包**的命令，安装到
> 项目后是 `<project>/.agent-bridge/bridge`（不在本插件的 `bin/` 下）。插件
> `bin/` 提供等价入口 **`orchestrate-bridge`**（转发到项目内 bridge），以下命令
> 两种写法等价：
> `orchestrate-bridge dispatch ...` ≡ `.agent-bridge/bridge dispatch ...`

## Use / don't use

**Use** when the task suits an isolated worktree, the 部门 is at capacity, or
`routing.json` says the seat's model is the better fit.
**Don't use** for: internal 部门 work → teammate (SKILL.md §7) · subsidiary offices
(Marketing etc.) → the existing mail lane · **never `Agent(...name=...)` a seat** —
that is the teammate path and mints a fake seat (right name, wrong model, no brief).

## One instance = one seat

`docs/board/seats/<name>.json`: `name` · `employment` (hq 总部 · subsidiary 子公司 ·
contractor 外聘/合同工) · `employer` (which org it works for) · `dept` binding ·
`platform` · `model` · `capabilities` (`multimodal` / `context_tokens`) ·
`worktree`. Several contractor sessions working at once → register distinct
花名 (Vera · Lisa · Eric…, the CEO's call), each with its own worktree and
`active_card`; the Boss Board renders them as `dept [花名]`, e.g.
`Backend-IO [Vera]`.

## Dispatch — the one command the CEO must remember

Shortest form; the script does everything else:

```
.agent-bridge/bridge --agent claude dispatch --seat <花名> --task "..."
```

Automatically: resolve the seat's `dept` binding → look up model/effort in
`routing.json` → write the card (`dept` unchanged, `seat:` recorded) → write the
dispatch mail → create/reuse the worktree → open a **headed** terminal (interactive
codex). `--no-open` skips the window. **Never headless.**

Cards with a full SOP: write the card first (`what` / `done-when` complete), then
`dispatch --card <id> --seat <花名>` — the SOP stays in the card; the command line
carries only the id, so punctuation/quotes cannot truncate it.

Optional overrides (skip unless needed): `--class` · `--model` · `--effort`,
recorded on the card for recruit to absorb. Capability constraints (Dial 3 in
`model-routing.md`) cannot be overridden.

## Claim · report · close

On duty: read AGENTS.md → `bridge mail sweep --mark-read` →
`bridge work claim <id>` — the card's `seat:` field targets it; a same-部门 seat
cannot claim another seat's card.
Done: `bridge work submit <id> --msg "..."` → card `review` + mail to CEO.
**Closing is the CEO's job; a seat cannot close its own card**: after the review
gate, `bridge work close <id> --as ceo --sha <sha>` (card → `done/` + BACKLOG).

## Gates

**Done-AND-correct**: card `review` → review gate (Auditor or Boss sign-off) → CEO
close. No close before review; nothing counts until closed.
**Stuck**: a seat silent for a round, or a card stuck in `doing` → one mail nudge;
still silent → escalate to the Boss. Never hand-edit card status.

## Most likely to break

**The CEO treats a seat as a teammate and `Agent()`s it.** Reach for `dispatch`,
not spawn. The seat's model line is the only evidence: wrong → it's a fake seat,
kill it.

**Keep this file current**: protocol, commands, or capability constraints change →
edit here; SKILL.md carries pointers only.
