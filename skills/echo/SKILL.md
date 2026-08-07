---
name: echo
description: 回声 — read the Boss's ask back to them as a table before any work is dispatched, so they can correct a misread by number instead of discovering it after the work ships. Invoke when they ask for an echo / a read-back / 读回来, when they type "echo", and proactively on a marked screenshot or a multi-part description before dispatching.
---

# 回声 — read the ask back before you dispatch

The Boss has asked for a read-back (or you are about to dispatch a marked-image or multi-part ask). **Post the table, end your turn, and dispatch on the next one.** The turn break is the whole point: it is their chance to say "3 wrong".

**Format, the three load-bearing columns and every rule → `orchestrate/reference/dispatch-artefacts.md` §1.** Do not restate the doctrine here; read it.

```
### 回声 #<task_id> · <the ask, one line>
| # | what they asked | which contract row | what I'll change | what it'll look like after | if you don't reply |
|---|---|---|---|---|---|

Open questions I couldn't resolve from the ask alone:
- <question> → my default: <what I'd assume>
```

## The four things that make this worth their time

1. **One row per ask, never per message.** A marked image gives a row per mark; a description gives a row per requirement you extracted. **Separating braided asks is your first job** on a text ask, before you bind any of them. A merged row is where a misread hides.
2. **`which contract row` is the binding step.** The matrix says what correct behaviour IS, but **only they can say which row an ask is about.** Bind it wrong and the work passes L2 and is still wrong on their eyeball. Cite the row; where there is none, write "no row" and state what you are inferring.
3. **`what it'll look like after` describes what they will SEE**, not what you will do. They catch wrongness instantly by eye, and this is the only way they get to use that before the work exists rather than after it merges.
4. **`if you don't reply` states your default**, so **"3 wrong" is a sufficient reply.** Design for a two-word correction, never for a paragraph.

## After you post it

- **They reply, or says nothing** → dispatch. Their word is the green light; do not ask again and do not defer.
- **They correct a row** → fix that row's binding, dispatch the rest.
- One read-back covers the whole round however many cards it holds. Their next *new* ask is the one that deserves another.
- **Wait for their explicit word only** where the ask-to-row binding is genuinely uncertain, or the change is hard to reverse.
