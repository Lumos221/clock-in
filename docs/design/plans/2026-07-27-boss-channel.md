# Boss channel — one destination, and a pointer instead of a stream

**Status:** in build (2026-07-27)

## Problem

A terminal transcript is a *stream*. Anything the founder must read arrives interleaved with progress narration, and scroll position is destroyed every time new output lands, so re-finding a decision means scrolling twice and often missing it. The Boss Board is a *place*: persistent, ordered, re-readable. It should be where every founder-facing item lives, and it is under-used instead.

Two causes, and only one of them is the channel:

1. **The feed is fire-and-forget.** Items reach the board as `@BOSS[...]` markers parsed out of assistant text at turn end. A missed parse loses the item silently: nothing returns an error, so nobody learns the message never arrived.
2. **Nothing announces a post.** The panel opens only when a post happens to start the server. With no signal, the founder stays in the terminal; because that is where they are, agents keep writing to the terminal. The channel is not what keeps the board empty, the missing signal is.

Fixing (1) alone leaves the board just as unread.

## Design

One destination, three supports.

### 1. Substrate: an MCP tool, not a text marker

The plugin ships an MCP server (`.mcp.json` at plugin root, started automatically with the plugin). It exposes a posting tool whose arguments are validated.

A tool call beats a marker on three counts:

- **A receipt.** The caller gets a return value, so a rejected or failed post is visible rather than silent.
- **A schema is the noise filter.** Prose cannot be validated; a tool call can. A required one-line ask with a hard length cap, an optional detail, a closed set of kinds, and a required speaker are enforceable at the boundary. Malformed posts are rejected with a message that teaches the shape.
- **It works from a subagent session** without depending on that session's Stop dispatcher running, and it is hookable as a real event.

The kind vocabulary refines the store's existing binary split (anything not `info` files under "Needs you") into `decision` / `blocker` / `signoff` / `info`. Nothing not-`info` changes section, so this is additive with no migration, and it gives the display something meaningful to group by.

### 2. Signal: a pointer, never the content

- **Desktop notification** when an item lands, throttled so a batch of posts is one banner rather than five.
- **One line at turn end**: how many are open and how old the oldest is. No content in the terminal, only the pointer. This is the one thing a stream is good at.

Phone push is explicitly dropped: it was named once in a SOP and never wired, so it was a promise the system did not keep.

### 3. Doctrine, enforced by a nudge and never by a block

The terminal cannot be policed directly. What can be set is what agents are *told* belongs where:

- **Board**: anything needing a decision, a signature, an unblock, or any durable fact worth re-reading.
- **Terminal**: progress, and a closing pointer to the board.

Enforcement is a Stop nudge. **It fires on durable state, never on prose.** A card that went blocked, or passed review and now waits on the founder, is a fact on disk; "this turn addressed the founder" is a guess about a transcript nobody controls, and gates built on that guess have already had to be retired once. State-based nudging covers the cases that matter and cannot misfire into blocking real work.

### 4. Display

The board stops being a status page and becomes the primary interaction surface, so it needs its own pass. Deferred to a separate round with side-by-side previews, since the founder's eye is the acceptance test.

## Non-goals

- Blocking a turn end, or any hard gate on posting.
- Parsing prose to detect founder-facing content.
- Any new surface that must be watched to work.

## Build order

1. ~~MCP server + posting/resolving tools, with validation.~~ done
2. ~~Desktop notification on arrival.~~ done, folded into (3): one reading, two surfaces.
3. ~~Turn-end pointer line.~~ done
4. ~~Doctrine into the SOP and the channel reference.~~ done
5. ~~State-based Stop nudge.~~ **dropped as redundant**, and worth recording why: an unmarked trailing question is already blocked once by the ask nudge, and cards nobody advances are already surfaced by the stage-stall sentinel. A third sentinel over the same facts would be noise wearing the costume of rigour.
6. Display pass, with previews. ← next, and the only piece that needs the founder's eye
