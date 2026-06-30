---
description: Open the Boss Board (live "needs-you" panel), or add/resolve one of your own items.
---

The **Boss Board** is your live panel of every pending ask for you across panes. Run the matching command from `$ARGUMENTS`:

- **no args** → just surface the panel:
  `orchestrate-board open`
- **plain text** (a thing you want to raise/discuss) → add it as your own item and open the panel:
  `orchestrate-board add --dept Boss --kind discuss --text "<the text>"`
- **`done <id>` / `park <id>` / `reopen <id>`** → change an item's status:
  `orchestrate-board <done|park|reopen> <id>`
- **`list`** → print the current items in this pane (no panel needed):
  `orchestrate-board list`

Panes raise their own asks automatically with `@BOSS[<dept>]: <ask>` (a Stop hook captures them) and resolve with `@BOSS-DONE[<dept>]` — you don't run those; this command is for *your* side.

$ARGUMENTS
