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
  For `done`, if the Boss's words state the outcome, record it so the resolved row (Information column → History) collapses to it:
  `orchestrate-board done <id> --sum "<one-line outcome>"`
- **an FYI of your own** (no decision needed — it belongs in the Information column):
  `orchestrate-board add --dept Boss --kind info --text "<the fact>"`
- **`direction <text>`** → pin the product's standing direction (e.g. the launch checklist) above the panel; `direction clear` removes it:
  `orchestrate-board direction --text "<text>"` / `orchestrate-board direction --clear`
- **`list`** → print the current items in this pane (no panel needed):
  `orchestrate-board list`

Panes raise their own asks automatically with `@BOSS[<dept>]: <ask>` (a Stop hook captures them) and resolve with `@BOSS-DONE[<dept>]` — you don't run those; this command is for *your* side.

$ARGUMENTS
