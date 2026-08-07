# <项目> · DECISIONS — decision log

> **What** — every significant decision + its *why* (architecture · scope · a resolved fork · a 法务 call).
> **Who** — the CEO appends one entry, however the call was reached (inline · 例会 · 董事会).
> **Rule** — decisions live here (versioned, dept-visible), **not** in session memory.

Entry = `## <date> · <one-line decision>` + **Why** + **Impl** + **By** (+ optional **Affects**). Newest on top.

> **Every behaviour-changing ruling carries an `**Impl:**` line** — exactly one of: `#<id>` (the card that lands it — TaskCreate it in the same breath) · `parked: <why + where tracked>` · `none-needed` (no code/copy changes). Implementation "queued" only in prose is silent loss: nothing tracks it, the dead behaviour stays live and re-teaches the dead design. **A superseding ruling's card must also name the removal of the old path** — code outlives decisions unless a task says "delete it". (A session-start sentinel flags recent entries missing **Impl**.)

> **Key/binding decision?** tag the headline with its topic-key so it earns a read-first `docs/CANON.md` row: `## <date> · [topic-key] <one-line decision>`, then register it once with `@CANON[<dept>] <topic-key> → DECISIONS (affects: …)`. CANON greps the **topmost** `[topic-key]` and mirrors this headline. Tactical/local decisions stay **untagged** (log-only). To supersede: add a **new** tagged entry on top + re-register.

---

## <YYYY-MM-DD> · <decision in one line>

- **Why:** <the reasoning · what it rules out>
- **Impl:** <`#<card-id>` · `parked: <why>` · `none-needed`>
- **By:** <inline CEO+Boss · 例会 · 董事会>
- **Affects:** <what changes downstream, or —>
