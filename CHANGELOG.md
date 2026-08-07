# Changelog

All notable changes to **clock-in** are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com); this project uses [semantic versioning](https://semver.org)
(`0.x` = pre-1.0, still evolving).

## [0.9.140] — 2026-08-07
### Changed
- **The instructions no longer assume who you are.** Every shipped instruction file, agent definition, MCP tool description, hook message, comment and test described the owner of the company in the third person feminine — 380+ passages, including the board channel's tool schemas that every agent in every installation reads. That is one person's setup written into a general tool: it tells a stranger's assistant something untrue about the stranger, and it does so in the schema text an agent is most likely to imitate. All of it now says "the Boss" or they/them. Field anecdotes that named a particular installation — a real project name, a real board, a real screenshot — keep the engineering fact and lose the identification. No rule changed, only who the rules assume they are talking about.
- **A pre-push guard, because remembering is not a mechanism.** `.githooks/pre-push` scans the tree AND the commit messages a push would publish against `private-patterns.txt`, and refuses. Enable with `git config core.hooksPath .githooks`. It **fails closed**: it will not run at all unless a self-check confirms the scan can still find a string known to be in the tree. That check exists because the first version passed its regex to `git grep` after a bare `--`, so git read it as a pathspec, matched nothing, and waved everything through while printing nothing — a guard that can be wrong in the quiet direction is worse than no guard, since you stop checking by hand. False positives get a line in `private-allow.txt` rather than a looser pattern: an exception blinds one approved case, a loosened pattern blinds every future one.
- **The inspector stays on `opus`, whatever it is looking at.** One of the two paths to the top tier was a repeat-bounce 复盘 escalating the independent inspector. A 复盘 is detection work, and detection is exactly where more tier buys no recall (the same finding behind the effort cap already in force); its verdict is a root cause plus a fix, not a design. The path is deleted, leaving one situation that can justify the ask at all: a producer that has already run at `opus` and bounced again on competence.
- **The top tier is never routed, only approved.** Two named triggers used to let the manager spend `fable` on its own judgement — a weekly-capped tier whose consumption is invisible until the cap is gone, which is the one resource where a correct-looking decision and a silent loss are the same event. Both triggers survive as **grounds for asking**, and neither is grounds for spawning: post one `@BOSS` line naming what you would spawn, which bar it clears, and the fallback you will run meanwhile, then get on with the round. `pretool_spawn_guard` holds it mechanically — any spawn naming `model: "fable"` is refused unless the same call carries the literal `BOSS-APPROVED-FABLE`, and it is judged on **one-shots too**, since the recurrence trigger routes a one-shot reviewer, which was precisely the spawn shape the old tier guard returned before it ever saw. The owner's own standing pin in a department brief is untouched: that spawn names no model, so the guard never sees a value to judge. `routing.json` may not carry the tier at all — a table exists to be applied without thinking, and this is the tier that must never be spent without it. 6 tests.
- **One way to run the company.** The org had two operating modes selected by the manager's own model, and the manager was asked to identify its model at startup to pick one. The distinction had already collapsed in practice — every dispatch artefact that mode invented had been promoted to the default spine, and the craft parity the other mode rested on stopped existing when department heads went a tier below the manager — so what remained was a fork whose two branches read the same, plus a startup step that could be skipped and twice was. Now: **nothing branches on the manager's own tier**, and the five rules that were genuinely mode-specific are folded into the spine that always applies — the pane holds artefacts and never raw code · visual acceptance goes to the owner's eyes rather than the manager's · one plan review per round rather than one per micro-spec · the `Fixed vs free` split is normally weighted toward FIXED, since heads run below the manager by default · the top tier needs the owner's word. `reference/brain-regime.md` and the session-start mode-arming hook are deleted rather than deprecated.
- **`SKILL.md` no longer states a routing rule.** Tier pins, the effort ladder and how effort reaches a seat had leaked into the always-loaded spine, where they were a second copy of `reference/model-routing.md` free to drift from it — and one had: a mode-arming line prescribed a tier the routing file no longer defaulted to. The spine now carries the collaboration shape and points once; the routing file answers every question about which model runs what. A stale `Config 2` anchor in `dispatch-artefacts.md` pointed at a section that no longer existed and now names the rule it meant.
- **Public README.** The "same trigger, two companies" section described picking between two org shapes by model, which no longer exists, and the feature line still claimed department heads run at the manager's tier, which stopped being true in July. Both rewritten around what the product actually does, including the approval gate on the top tier.

## [0.9.139] — 2026-08-07
### Added
- **A queue deeper than its seat can close is flagged at turn end.** A seat retires at `seat_cards_max` closed cards, and a successor seat cannot claim cards owned by the retired handle (the owner match is exact) — so every card queued past the seat's remaining room is a re-assignment debt being written in advance. The closed-card counter watches the past; nothing watched the queue: the field case was five cards assigned onto one seat with the counter at zero, in silence. The capacity sentinel now counts open cards per exact handle against the seat's remaining room and says which handle holds how many, once per state. A fat seat is skipped — it already gets its own order, and two alarms about one desk teach the reader to skim both. Mutation-verified.
### Fixed
- **The banner's click now lands beside the board instead of in Script Editor.** Follow-up to 0.9.137: on current macOS this notifier generation can never register its own bundle (deprecated API — the permission prompt does not exist), so the native click-through path is unreachable and the spoofed sender is permanent. A spoofed click can do exactly one thing, activate the sender — so the sender is now the DEFAULT BROWSER, read from the LaunchServices handler record: banners deliver under a grant that exists, and the click surfaces the window where the board tab already lives. Script Editor stays the fallback when the browser choice cannot be read.

## [0.9.138] — 2026-08-07
### Changed
- **The lane filter multi-selects, and the controls sit on the title line.** Notion's filter idiom: the two aggregates (In flight, Everything) pick alone and close the menu; the five value lanes are checkboxes that union, and the menu stays open while they are ticked — which meant the open-state had to move out of the DOM and into state, since every tick rebuilds the header. The face names the selection (two lanes + how many more) with the combined count; an emptied set falls back to the In-flight default. Both controls moved up beside the section title, right-aligned, popovers anchored right. Union, fallback, face and stay-open are test-pinned; layout screenshot-verified in both themes.

## [0.9.137] — 2026-08-07
### Fixed
- **Clicking a banner now opens the board — it never did.** The notifier posts under a borrowed Apple bundle so its banners actually appear (its own bundle was unregistered and macOS dropped every post silently), but the borrow has a cost the code never priced in: with a spoofed sender the click is delivered to the spoofed app, and the open-URL action is discarded. So the claimed click-through was structurally dead from the day it shipped. Posting natively is what makes the click land, and that needs the notifier's own bundle registered once in Notification Centre — the code now checks for that registration on every banner (fresh, so a grant takes effect inside a long-lived daemon) and posts natively when it is there, falling back to the borrowed sender, banners-but-no-click, until then.
- **Opening a conversation parked their mid-thread instead of on the newest message.** The jump to the bottom measures the thread's height, and a late-loading image grows the thread after the measurement — each retry warmed the image cache, which is why repeated clicks crept closer to the floor. Every image that finishes loading now re-pins the scroll while they are still near the floor, and never after they have scrolled up to read.
### Changed
- **The task header states the choice; a popover holds the alternatives.** Seven lane pills and four sort links spread flat across the header made every option shout on every visit. The header now reads as two quiet controls — the current lane with its count, the current sort — each opening a Notion-style menu with the alternatives (lanes carry their counts). Screenshot-verified in both themes; the control's shape is test-pinned.

## [0.9.136] — 2026-08-07
### Fixed
- **The alias alarm flagged the CEO's own review markers.** The CEO's own cards — specs, plans, design docs — gate through the same output review as everyone's and file their markers under CEO, a handle that sits in no roster and has no agent file, so the unknown-prefix detector read a deliberate self-produced card as a count-splitting alias. CEO is now a built-in legitimate prefix, added past the detector's arming gate: baked into the handle registry itself it would have armed the detector on rosterless projects, where it is deliberately off. Bounces on such cards already bucketed cleanly per card, so the circuit breaker counted and still counts them; only the false alarm is gone. Test-pinned three ways: a CEO marker no longer flags, a true alias still does, two bounces on one CEO card still trip the breaker.

## [0.9.135] — 2026-08-07
### Added
- **Task-card chips wear the department plus the seat's given name, not the seat number.** A seat's handle carries the number of the card it was opened for (`Frontend-1099`); on the card face that number is noise twice over — the card already shows its own number, and two numbered seats of one department drew two colours for what reads as one desk. The chip now strips the trailing number, keys one hue per department, and appends the seat's display name from the spawn record (`Frontend · Lisa`), joined by the handle written on the card or by department plus the card's own number. The name is picked by whoever opens the seat, never generated by code: a name the dispatcher didn't choose is a name the dispatcher cannot resolve when it is spoken back — the doctrine now makes naming part of every department spawn. Seat records also join the panel's change detection, so a newly recorded name redraws the board instead of waiting for unrelated news. Strip and join are test-pinned and mutation-verified.

## [0.9.134] — 2026-08-07
### Changed
- **The instruction files said their reasons twice and their longest rules in one breath.** The review agent carried the same argument for the contract-citation bar at both of its gates; the main orchestration file restated, column by column, a doctrine a reference file already owns; two sections of the operating contract had grown into single paragraphs braiding six distinct rules each. Each reason now lives once, at the gate that acts on it, with a pointer from the other; the braided paragraphs are split into one rule per line, each still carrying its reason. No rule was dropped and no threshold moved — only the wording that carried them is shorter.
### Fixed
- **A template shipped an inline comment inside its frontmatter tool list — in the one place another file in this repo documents that the loader reads such comments as tool names.** Every agent generated from it would have carried a corrupt tool list. The comment's content moved into the body, where its sentence was already half-written.

## [0.9.133] — 2026-08-07
### Added
- **The routing table was binding on one dispatch path and advisory on the other, and the advisory one carries most of the work.** A department's model and thinking level are written down per department and per kind of card; the script that hands work to an outside terminal reads that file and applies it, while an ordinary in-house dispatch relied on somebody remembering to look. A rule nobody consults is decoration. Now the one case nobody catches is refused: a dispatch that names no model at all, inherits whatever the department's standing pin says, and opens a desk a tier under what that kind of card actually needs — silently, and looking correct from the outside. **Naming a model always passes**, because naming it is the decision the rule exists to force; only the silence is blocked. **The refusal is two facts and a parameter** — what this dispatch will open on, what the table says for this kind of card, and to pass the model. It names no value: which tier a card wants is the office's call, and a refusal that answers the question has answered the one it was built to make somebody ask. It also quotes the single row in question, never the file — a reader mid-dispatch should not have to find their own line in a config dump. No table, or a class name that is not in it, stays silent: the table is the office's own note to itself and a typo in it must never stop the work. Dry-run against a live board: seven departments, zero refusals on the ordinary path, and a refusal on exactly the four cards whose kind raises the tier.

## [0.9.132] — 2026-08-06
### Fixed
- **The routing rules told a department head to do one thing in one section and the opposite in another.** One said routing is a lookup and not something to work out per card; another said the level is decided per card, every card, and that a rule nobody consults is decoration. Both were true of different halves of the same job and neither said so. They are one rule now: look it up, then ask whether this card is the usual card, and an exception is an override that has to leave a trace or the table rots.
- **The rules described a per-department thinking level that does not work.** They said a department is given its level when it is opened, that opening one without a level is refused, and that something carries the level through afterwards. None of that is live: the platform hands a department the main session's level and drops anything the department's own file says, and the mechanism built to work around that was withdrawn — typed into a working pane, the command waits for the current turn to finish, and a department's first turn is the whole card, so it arrived after the work it was meant for. Three files repeated the retired version. They now say the true thing: the round's level is the one you set on yourself before dispatching, and the single-seat command is a mid-life correction on a long-running desk, not configuration.
- **A summary of the routing table in another file had drifted into being wrong** — it still named a tier for the legal desk that was changed weeks ago. Replaced with a pointer, because a summary of a routing table is a second routing table.
- **Seat capabilities were being defined in two files at once.** The routing table now says which seat serves which department and at what tier; the seat registry says what that seat can do. One fact, one file.
### Changed
- **The routing reference is a third shorter while carrying more.** It had grown paragraphs restating its own tables, the history of each decision, and the same instruction in three places. Now it is the three dials, one lookup rule, four tables and the hard rules that cannot be derived from them, with the reasoning kept only where the rule fails without it.

## [0.9.131] — 2026-08-06
### Changed
- **The priority tag says the level and nothing else.** It read `P0 urgent`, `P3 nice-to-have` — three quarters of its width restating what the level already means to anyone reading the board, on every row, beside an id tag and a department chip. The tag is now just `P0`; the word is what guides whoever sets the level, so it lives on the hover and in the rule that hands the levels out.
- **P0 looks like P0.** It and P1 were neighbouring tints of the same wash, a difference only a colour picker could make, on the one distinction that means drop what you are doing. P0 is a filled badge now, in both themes; P1 through P3 stay tints of the same ramp so the eye still sorts them without reading them.
### Fixed
- **A card opened in full did not show it was a bug.** The grid drew the bug tag beside the priority; the detail view drew only the priority, so opening a card to look closer lost a fact the row had.

## [0.9.130] — 2026-08-06
### Changed
- **Everything the system says at a turn end was a lesson; it is an order now.** Twenty-nine messages carried the reason the check exists, the incident that motivated it, and a note that it only fires once — all of it read in a live turn by someone whose job at that moment is to act, and none of it changing what they should do. One ran to eight hundred characters to say "put this question on the board". They now say what is true, with the exact ids and paths, then what to do, then a prohibition only where the wrong fix is tempting — leaving each one roughly a third shorter and the longest less than half what it was. The reasoning has not been deleted, it has moved to where the person maintaining the check reads it. Three tests that pinned the old wording now pin the thing the wording had to carry, so a future trim cannot quietly drop a prohibition.
### Added
- **A length budget, because prose grows back one clause at a time and no reviewer objects to a single clause.** No single message may exceed 400 characters, and the total across every hook is capped just above where this sweep landed, so adding a new one is a decision rather than an afterthought. A third test checks the budget is actually finding the messages — a limit that matches nothing passes forever.

## [0.9.129] — 2026-08-06
### Changed
- **The field sweep no longer overwrites a value it cannot read — it asks about it.** A card's priority holds a level, and a level that arrived in words rather than in the notation (`low`, `normal`) was cleared, with the original filed to a log nothing opens, by whichever session happened to run next. So a level set at 23:52 was gone by 00:07, in a sitting that had already ended, with nobody told. The clearing was never a repair either: it was a guess at what someone had meant, and it guessed both ways — `low` says the opposite of unset, and a level written with its reason beside it was demoted for the sake of the parenthesis. Nothing forced it, because every reader already treats an unreadable level as unset: the card behaves the same whether the words stay or go. Now they stay, exactly as written, and the desk that owns the field is told at the end of the turn — which card, which field, what it says, and the four levels to choose from — while whoever wrote it is still there. Said once per state, not every turn. The sweep still does the part it can do without guessing: a status written as a sentence collapses to its keyword, and a level with its reason attached keeps the level, both with the original preserved on the card.

## [0.9.128] — 2026-08-06
### Added
- **The card's own fields now have one definition, next to the rules for how a card is born.** A card arrives with five fields filled and four placeholders, and what counts as a valid value was scattered: the priority levels and the bug tag lived inside a long paragraph about dispatch, the status words in the operating contract, and nothing carried the rest. None of it was visible at the moment someone was filling a card in, and nothing checked the value on the way in — the only feedback was the hygiene sweep clearing the field hours later. One table now names the nine fields in the order they are written, who owns each, and what a legal value is, and it says the part that had been costing the most: a value the machine cannot parse is not a partial answer, it reads as set and behaves as unset. The dispatch paragraph no longer restates any of it and points here instead, which also shortens the longest line in the dispatch rules. A test pins the priority levels named in the documentation to the levels the sweep accepts, since the gap between those two is what the previous fix was.

## [0.9.127] — 2026-08-06
### Fixed
- **Twelve cards were quietly stripped of the priority somebody had deliberately set.** The dispatch rule hands out four levels, P0 urgent through P3 nice-to-have, and the board draws all four with the level named on the tag. The nightly field-hygiene sweep accepted three. So a card marked P3 — the level the rule itself says to use for work that can wait — had the field emptied hours later, with only a one-line note in the card's body to say it had happened. On one board: ten of them, including a card whose title, summary and completion condition all record the level it had been given by hand, next to a `priority:` reading unset. A level written with its reason beside it (`P0 (closes the recurring family)`) lost the level too, because the whole field was discarded for the sake of the parenthesis — a demotion nobody chose. Four levels are now accepted, a level written with an explanation keeps the level and moves the explanation to the note, and an invented value (`low`, `normal`) is still cleared, because those carry no order and nothing can sort them.
- **A card opened in full showed a priority tag only for the top two levels.** The list showed all four; the detail view dropped to an older rule of its own and rendered nothing for the rest, so opening a card to look closer showed less than the row it was opened from.

## [0.9.126] — 2026-08-05
### Fixed
- **Cards nobody had ever started were reported as reviewed and waiting to be merged, and the gate that stops unreviewed work would have let them through.** A review record can be filed under either of two numbers: the card's permanent one, or the working number the platform hands out for the duration of a session. Working numbers are handed out again to later cards, so a match on one is a guess, and the record's date is what tests the guess. A record can also name the change it judged, and that name outranked the date — correctly, because a record filed under a permanent number is already known to belong to the card and its date is the only thing left in question. Filed under a reused number it is not known to belong to anything, and the change it names is still in the repository whoever it belonged to, so the test that was supposed to catch the borrowed number was answered by a record about someone else's work. On one board: six cards, none of them started, none with a record of their own anywhere, all three readers of the rule — the panel, the end-of-turn stall report, and the completion gate — agreeing they were finished. Evidence of the change now settles a record already tied to the card; a record matched only by a reused number must clear the date as well, which is the test that separates a verdict minutes old from one weeks old.

## [0.9.125] — 2026-08-05
### Fixed
- **A finished card could not be closed, and the reason it gave was the wrong one.** A review record names the change it judged twice over — the commit, and a fingerprint of that commit's content — and the reviewer writes both by hand. When those two disagree, the gate was reading it as "the change is gone" and refusing the card forever, while telling the office the record was older than the card. It was four minutes old. That sent someone hunting a clock problem that did not exist. A record whose two halves contradict each other proves nothing either way — it cannot even say which half is the mistake — so it now counts as no fingerprint at all and the ordinary date rule decides, exactly as it does for every record written before fingerprints existed. A record naming a change genuinely absent from the repository is still refused. The gate also says which of the two it found, because a gate that misnames its own reason costs more than one that refuses.
### Added
- **Messages were being sent to desks that do not exist, and the send said it worked.** A desk's mailbox is a file named for its exact handle, so a message to `Frontend` goes nowhere at all when the desk is `Frontend-1096` — it is written to a box nothing reads and nothing clears, while the send returns a receipt and the sender moves on. Found on one machine: 117 such messages, 52 in a single live team, and thirteen of those were work assignments to a desk that was sitting right there waiting. Nobody had been told, because nothing was looking. Now something is: at the end of a turn the office is shown what never arrived, separated into the ones whose desk is live under a different name — those need re-sending — and the ones that arrived after their desk had gone, which need reading but cannot be re-sent. It reports and never blocks; what to do about a given message is a judgement, and finding them was the part nobody could do by hand.
- **Half of one project's review rounds were paperwork, and the paperwork was being billed as review.** A bounce that changed zero bytes still cost a full round: an expert reviewer opened, read, wrote its refusal, and the work came back to fix a line that could have been fixed before anyone was asked. Two of those refusals are now made at the moment the review is requested, before anything is opened — the request must name the task it is about, and any file the card points to as its evidence must actually be there. Neither is a new requirement; both are refusals the reviewer already makes, now costing nothing. The gate is untouched: the same things are refused, by the same standard.
- **A one-shot worker was being handed the rulebook for a job it does not have, including a way to put a question in front of you that it could not stay around to hear the answer to.** The operating contract every worker reads at startup described one life: claim from a queue, report to the office, hold a pane, answer when asked to shut down. A worker spawned for a single piece of work has none of those — it does its piece and returns — so a quarter of what it read was instructions it could not follow, on every single dispatch. The contract is now in two halves, and the command that serves it works out which kind of worker is asking by looking at how that worker was started, rather than asking it. Standing desks get both halves. Everything else gets the core, a third shorter, and it says plainly that a question for you goes into its result for the desk that sent it to raise and own — the test being whether it will still exist when you answer.
- **Every desk was thinking as hard as the busiest one, and none of them had been asked to.** A department gets no thinking level of its own: the platform drops that setting on the way to the pane and hands the desk whatever the main session happens to be at. So a task desk whose whole job is mechanical writes paid for maximum deliberation, and a department on a genuinely hard card could not be given more — invisibly, because nothing anywhere showed the level. Opening a desk now states it: `effort=<low|medium|high|xhigh|max>` written into the spawn, refused if missing, and carried out on that desk alone. A few characters on a call that was already being made, and no default deciding quietly on anyone's behalf. Changing a running desk is still possible (`orchestrate-effort <seat> <level>`) but costs it a re-read of everything it has been told, which is why the choice belongs at the opening and then holds.
- **Model and how-hard-it-thinks now have a written decision rule instead of a list of pins.** Which model comes from how much judgment the task leaves open; how hard it thinks comes from how much searching is needed before committing. The concrete tables are published, measured ones, cited to their sources, rather than invented here. Review and bug-finding are capped: past a point, more reasoning trades away the defects it catches for a cleaner-looking list, which is the wrong trade for a gate.
- **Experts can no longer be opened as departments.** An expert given a name became a standing desk holding a pane it had no card for, and lost the thinking level its own file specified, because that only survives on the one-shot path. Naming one is refused at the spawn with the fix in the message, the same way the reviewers already are.
### Fixed
- **A desk could acknowledge being shut down, politely, and keep running.** Shutting down is the platform's own protocol, but the instructions for it live inside a tool whose details load only on first use — so a desk released before it ever reported anything could neither read the rule nor follow it, and answered with a sentence instead. It kept its pane and its name while the office read it as released. A release is now confirmed by the desk being gone rather than by what it said, which also catches the case where a correct answer fails to end it.
- **A brief written and used in the same sitting produced a desk that was not that brief.** New role files only take effect after a restart, and using one early does not fail: it takes the name, takes the pane title, and quietly falls back to a default model with none of the role's instructions. The result looks correct from the outside. Authoring a role now ends by handing over the files, and the check for whether one loaded is its model, not its name.
- **The legal desk ran on the wrong tier.** It owns the line that cannot be crossed, where a wrong call is a liability rather than something to redo, and it is now pinned accordingly.

## [0.9.124] — 2026-08-05
### Fixed
- **Only one of the three things you can send was ever kept.** A reply was recorded as the item's outcome; a question asked about an item, and a message written to a department, went to the session and left nothing behind. The thread showed the item, then the session's answer, with the words that provoked it missing from between them. Everything sent is now logged with where it went and when, and drawn in the thread: questions under the item they are about, quoting it; messages with nothing bound standing on their own, in the order they were sent. Answers from before the log still draw from the old field, so no history is lost.
- **A question also failed to redraw the page.** An ask changes nothing on its item — it stays open, unread, untouched — so the "has anything changed?" check said no and the thread never rebuilt to show it. The send log is part of that check now.
- **Opening a conversation crawled the whole thread instead of landing on the newest message.** The thread column sets `scroll-behavior: smooth`, so assigning a scroll position animated it: the view travelled from the oldest message to the newest, which is exactly the scrolling the jump exists to save. It is instant now, and re-applied on the next frame because the thread is still growing when the jump runs.

## [0.9.123] — 2026-08-05
### Reverted
- **`@BOSS-DONE` closes an item again, whether or not it has been answered.** 0.9.122 refused it on answered items, which was a misreading: the duplication being reported was prose in the terminal repeating an answer already posted, not the marker. Refusing a verb several paths depend on to close their own asks risked breaking the register to fix something that was not broken there. Replies and closing notes already live in separate fields, which was the actual fix.
### Changed
- **Posting an answer and then explaining it is writing it twice.** The rule said not to write it twice; it did not say that a recap counts. After a marker lands, prose that walks through the same content — a fuller version, the same answer told better — is a second copy in the one place that cannot be searched. The pane gets the ids and nothing else.

## [0.9.122] — 2026-08-05
### Fixed
- **A plain message went out as a question about an unrelated card.** With nothing bound, the composer hung the message on the conversation's newest live item and sent it as `<id> asks: <their words>` — so a fresh question arrived against a card from the night before that had nothing to do with it, and marked that card read on the way past. A message with no subject is now addressed to the conversation and to no item in it: it names no id, resolves nothing, reads nothing. A message to the CEO's own conversation also routes now; the CEO session registers no department name, so the roster lookup used to find no seat at all.
- **Send typed the message and left it unsubmitted.** The pane was given the text, then read once after a fixed 0.22s pause; a long message re-wraps the input box, and a terminal that had not finished painting inside that window read as "never took it", so the Return was withheld and the text sat there waiting for a keypress. The echo is now waited for rather than sampled, which is also faster when the paint is immediate, and a lost Return keystroke is tried once more. The interlock is unchanged: a pane that genuinely never took the text is still refused.
### Changed
- **`@BOSS-DONE` on an item they have already answered is refused, and the turn is told.** Their reply resolves an item as they send it, so the marker has nothing to withdraw, and what it carries is a second answer to the same question landing beside the Boss's own words. The rule already said DONE never follows their answer; now it cannot, and the message back names the move that does work: more to say is a new item, not a footnote on a closed one. The skill's board section says **answer once** in as many words — the full answer on the board, a pointer or nothing in the pane.

## [0.9.121] — 2026-08-04
### Fixed
- **A session closing its own ask erased the answer it had just been given.** The Boss's reply and the raiser's `@BOSS-DONE` note were written to the same field on the entry, and the board renders that field as their words, over their name and their clock. So a session that answered their and withdrew its ask in the same turn deleted what they had typed and left its own one-line summary standing in their mouth: the board showed a sentence they never wrote, attributed to them, and the real answer was gone from it entirely. They are two people and they now have two fields. A `DONE` cannot touch a reply, and the closing note renders as its own quiet line under the exchange, credited to whoever raised the item. The Obsidian mirror distinguishes them too: 答复 is theirs, 结案（提问方） is the raiser's.

## [0.9.120] — 2026-08-04
### Added
- **The capacity sentinel now notices work with nobody behind it.** It asked which desks had no card and never which cards had no desk, so a seat that died or was released while holding an in-progress card left that card claiming to be worked on indefinitely: not pending, so the idle-desk rule never offered it to anyone, and its owner absent from the team, so no idle judgement was made about it either. The card simply stopped moving and nothing said so. Found live, on a card that had sat behind a closed pane for three hours while the sweep reported a healthy team, because every remaining desk happened to be busy. Branch offices are exempt, since they run their own sessions and never appear in the team roster.

## [0.9.119] — 2026-08-04
### Fixed
- **Typing in the board's composer was interrupted every second or so, with nothing arriving.** The destination pane's iTerm session name is a Claude Code status line, and a working session keeps an animating braille spinner at the front of it. That name was part of the composer's "has anything changed?" check, so for as long as the session being written to was busy, the answer was yes on every poll and the box was torn down and rebuilt. The text was restored afterwards, but the caret jumped to the end and a half-typed IME word was already gone. The spinner is now stripped where a pane's name is read, so a name is a name.
- **The box is no longer rebuilt at all.** Restoring someone's typing is not the same as not interrupting it, so the textarea is now a permanent element: the context line, the hint, the placeholder and the Send label are each patched onto their own node, and the element being typed into is never replaced, for any reason. Its value is written only when the box is bound to a different item.
- **An unfinished draft did not survive a reload.** Staged answers have been written to the browser since the day a page of them was lost to a restart; the sentence still being typed was only in memory, so the automatic reload that follows a plugin update took it. It is now saved on every keystroke and read back on load, without ever overwriting a newer one.
- **The seat picker re-sorted itself while open**, for the same reason: panes were ordered by a name that was animating.

## [0.9.118] — 2026-08-04
### Fixed
- **A letter marked read stayed unread on the board.** Every view is cached on a stamp built from the paths its loader reads, and a directory contributed its own mtime — which moves when an entry is created, renamed or removed, and not when a file inside it is edited. Flipping `status: unread` to `read` therefore changed nothing the cache could see, so the mail lane and the branch-office badge went on reporting letters as unread until an unrelated letter arrived and shook the folder loose. Directories are stamped by their entries now: each name with its size and clock.
- **A turn-end notice could silently consume another one.** The Stop dispatcher runs fourteen checks in one process and delivered only the first that had something to say. Each of those checks writes its own one-per-state marker *before* returning, so a line the dispatcher dropped was a notice spent and never repeated: unread mail could sit unannounced behind a capacity line that happened to run earlier in the chain. Every line is delivered now, identical ones collapsed.
- **The conversation view threw on every redraw that carried new data.** It read two values describing where the thread was scrolled before the rewrite, and neither was ever captured. The throw landed inside the poll's own catch, so nothing looked wrong — but everything after it was skipped: the caret and focus restore while typing, the unread pointer, and the tab counts for Tasks, Departments, Decisions, Mail and Archive, which held whatever they had said when the board was opened. The thread now stays pinned to the newest message when they are already at the bottom, and keeps their place when they are not.
- **One function was declared twice in the panel script**, which a browser accepts by letting the second win, and which made the whole desk test suite unloadable — 34 tests red for a copy-paste, and the real drift underneath them invisible.
### Changed
- **The panel gate calls the draw functions with state loaded, twice per view.** It used to call them on an empty page, where the first line returns before any branch runs; and once each, which never evaluates the right side of a short-circuit. The ReferenceError above lived in exactly that gap. It also parses the script as a module, so a duplicate declaration fails the gate instead of the test suite.

## [0.9.117] — 2026-08-04
### Changed
- **One banner per arrival, not two.** `stop_board_pointer` has posted a desktop banner since long before the board announced its own arrivals (0.9.84) — so every item produced two: one at turn end reading `N on your board` under Script Editor's icon, and one on arrival reading `<Dept> · Needs you` under the board's, with them ringtone and a click that opens the panel. The older banner is retired. Its TERMINAL pointer is not: a stream is good at "N wait, oldest is 3h", which is the one thing a per-item banner cannot say.
- **The pane carries a pointer, never a copy.** The rule said prose alongside the board was fine; it is not, because then the same content exists in two places and the stream is the one that scrolls away. Post it, then say where it is — or say nothing.

## [0.9.116] — 2026-08-04
### Fixed
- **Every plugin update silently swallowed the next arrival — no banner, no sound.** `board_add` writes the entry and THEN calls `ensure_server`, which replaces a daemon left stale by the update; so the very entry that triggered the replacement is already on disk when the new watcher seeds itself, and it is filed as "was already there". Field case: `CEO-531`, written seven seconds after the daemon it had just restarted, never announced — and then twelve silent hours, because the next arrival came after the board had been quiet all night. An entry written within thirty seconds of startup counts as an arrival on the seeding pass now. Verified by replaying the exact sequence: write, restart, and the new watcher announces it.

## [0.9.115] — 2026-08-04
### Changed
- **The board rule is one line.** 0.9.113 added an exception for questions typed into a pane; 0.9.114 added a second sentence telling the reader not to make the distinction the first had introduced. Neither was needed: without the exception nobody would have thought to distinguish. 107 words to 35, and the duplicate in the department SOP — which already carried the same rule with the same reason — is gone.

## [0.9.114] — 2026-08-04
### Changed
- **Everything for the Boss goes on the board, wherever the Boss asked from.** 0.9.113 carved out an exception for questions typed straight into a pane. That was wrong twice: they may be typing there *precisely because* a board send just failed, and a session cannot tell where a message originated anyway — a rule that turns on a distinction nobody can make is a rule applied by guesswork. There is no case where the answer stays only in the terminal. Prose alongside it is fine; prose is never the delivery.

## [0.9.113] — 2026-08-04
### Added
- **A message that arrived from the board is answered on the board.** A reply opening `[Boss Board]` was written on the panel, so the panel is where the next question, result or decision is looked for — answering only in the terminal puts it somewhere unread. Written into the skill, the department SOP and the board reference, with its anti-trigger: live terminal dialogue is answered in the terminal.
### Changed
- **The Boss Board section of the skill is a table, not a paragraph.** It had grown into one unstructured block carrying the marker syntax, the DONE semantics, the Information lane, the collision nudge and the trailing-question rule — everything at the same weight, in a file that loads on every run. What to write is now three rows; the rules that qualify them are four bullets under it; the detail stays in the reference, which loads on demand.

## [0.9.112] — 2026-08-04
### Fixed
- **Still stuck on "Sending…", and this time the request was never made at all.** 0.9.110 claimed the send flag, ran three redraws, and only then released it and fired the request — so anything throwing in those redraws stranded the flag at true AND skipped the send. That is the exact picture: the tray sat on `Sending…`, the answer stayed in the basket, and 0.9.111's 45-second deadline could not rescue it because there was no request to time out. The claim is released in a `finally` now and the request fires after it, so no failure between the two can swallow a send.
- **A thrown handler no longer leaves the page looking merely idle.** An uncaught error surfaces as a toast naming it; a stuck state with nothing behind it is otherwise indistinguishable from a slow one.
- **The page is served `no-store`.** A version bump reloads the tab, and a cached page would have reloaded into the same old version forever.

## [0.9.111] — 2026-08-04
### Fixed
- **The page could sit on "Sending…" forever with no way back.** `fetch` has no timeout, so a request that never resolves leaves the `await` hanging: the `finally` never runs, `sending` stays true, and both the button and the tray are stuck until a reload. A server restarted mid-click is enough to cause it — the browser's request never reached the board at all, and the basket was still on disk afterwards. Every write carries an abort deadline now (45s for a send), a timeout says so rather than blaming the answer, and the tray leaves the sending state immediately instead of waiting for the next poll.

## [0.9.110] — 2026-08-03
### Fixed
- **Send looked as though it needed two presses.** It staged the answer, redrew the tray — complete with its own *Send to session* button — and only then fired the request. For the seconds the request took, the page sat there offering to send what was already on its way; the second press did nothing, because a guard caught it. The send is claimed before the redraw now, so no button is ever rendered for a message already sending, and the tray reads `Sending N…` with its button disabled until the request returns.

## [0.9.109] — 2026-08-03
### Fixed
- **The arrival watcher could get stuck seeding, and then announced nothing ever again.** `first = False` sat inside the try, so a single failure anywhere in the first pass — reading the store mid-save is enough — left the flag set, and every subsequent arrival was silently filed as "already known". The `except` swallowed the reason, so there was nothing to find. Together with the unregistered sender fixed in 0.9.108 this is why no banner had appeared all day: two independent silent failures on the same path. The flag is cleared outside the try now, and failures are written to `watcher.log` in the runtime directory instead of vanishing.

## [0.9.108] — 2026-08-03
### Fixed
- **Not one arrival banner had ever reached the screen, while the code reported success on every one.** terminal-notifier posts under its own bundle identifier, which macOS never registers in Notification Centre — it has no entry in `com.apple.ncprefs` at all — so the system accepted each banner (exit 0) and silently dropped it. Hours of arrivals, no banners, no error anywhere. They are sent under an application the system already trusts now; `-appIcon` still overrides the icon, so the board keeps its own mark.

## [0.9.107] — 2026-08-03
### Fixed
- **A message wore the time it was last touched, not the time it was written.** The clock read `updated || created`, and `updated` moves on any later touch — a read tick, a resolve, a batch sweep — so two messages written nine minutes apart both read 22:46 because one pass had touched them both. The clock and the day divider read `created` now. The Boss's own reply keeps `updated`: they answered when they answered, and that IS the update.

## [0.9.106] — 2026-08-03
### Added
- **Your own ringtones.** Drop `needs.<ext>` and `info.<ext>` into `~/.claude/clock-in-sounds` and an arrival plays them — any format `afplay` opens. The SERVER plays them, not the page, so they ring whether or not the tab is open, and ring once; the page's synthesised chime is retired, because a second voice beside the first doubled every arrival they was looking at. The banner drops its system sound whenever one of theirs played. No file, no change: the system sound still rings.

## [0.9.105] — 2026-08-03
### Fixed
- **The board rendered blank.** `drawComposer` read `ta` three lines before `const ta` — a temporal dead zone, which throws the moment the function runs and took the whole page with it. Both of the checks that ship a release passed it: a parse cannot see a dead zone, and a top-level execution cannot either, because a TDZ fires only when the function reading the binding is CALLED.
### Added
- **A panel smoke harness that calls the draw functions**, not just parses them. `panel_smoke.js` runs the page's script against a DOM proxy and invokes `drawComposer`, `drawDesk`, `renderTray`, `convoRail`, `convoThread`, `sendTo` and `marker`, failing on any ReferenceError. It is part of the suite, and mutation-verified: re-introducing the early read fails it with the exact error.

## [0.9.104] — 2026-08-03
### Fixed
- **"Send failed" on a message the session had already received.** The `try` wrapped the whole of the post-send handling, so any error *after* the request — a toast, a re-render, a copy — reported a failed send. The most expensive kind of wrong: it tells their to send it again. Only the request itself can fail a send now; anything broken afterwards says the message went and that the page had trouble redrawing.
- **Ignore left the ask on the desk.** It ticked `read`, which only folds an INFORMATION row — a needs-you item carries no such flag, so the toast claimed the item was gone while it sat exactly where it was. Ignoring resolves it now: off the desk, into History, marked `(ignored — no reply sent)`, and nothing is sent to anyone.
- **The Send button counted an answer that did not exist**, promising "Send all 3" under "2 answers staged". It added the composer to the total unconditionally; it only counts now when the box actually holds something.

## [0.9.103] — 2026-08-03
### Fixed
- **A send took seconds and gave no sign it was working, so it read as "click again".** The tray appeared the instant an answer was staged while the request was still in flight, and nothing said so. Three causes, all removed: the read-back is folded into the typing call (the pane is still checked BEFORE a character is typed — collapsing that would void the whole interlock); seat resolution sweeps every pane once instead of launching an osascript per candidate, which cost a second each; and Send now disables itself and reads `Sending…` until it returns.
- **The Send button named the department an item is signed by, not where the answer will land.** An item the lead relayed answers to the lead, so the button was promising the wrong destination. It names the real one now.
### Changed
- **Park became Ignore.** Read it, answer nothing, tell nobody — it leaves the desk the way an archived update does. `park` remains the CLI verb for a backlog hold, which is a different act.
- A failed send says the answers are on the clipboard as well as still staged.

## [0.9.102] — 2026-08-03
### Fixed
- **A delivery stopped at "typed" on a pane that had taken the text perfectly, so the Return was never pressed.** The echo check looked for the message's TAIL on the pane's screen — but `contents of s` returns the VISIBLE screen, and in a narrow pane (one sharing its width with a teammate panel) a long message wraps and its end is simply not on it. The check could not pass, ever, on exactly the panes a department works in. It now matches ANY sliding window of the message, which survives wrapping, truncation and a lost prefix — and still cannot match a pane the text never reached. A screen that changed into something that is not ours is refused outright.

## [0.9.101] — 2026-08-03
### Fixed
- **A page of staged answers could be wiped by a server restart.** Staged text lived only in memory and in a fire-and-forget POST, and `syncBasket` CLEARED the local basket to adopt the server's — so a restarted daemon, whose store had not yet caught the last POST, emptied everything typed. It happened in the field: a full set of answers, gone.
  - **The page is the record now.** Anything staged is written to this browser the moment it is staged, before any request can fail, and restored on load. The server copy is a convenience.
  - **Sync merges, never replaces.** The server can only ADD what this browser has not seen; it can no longer remove anything.
  - **Staging also reaches the clipboard**, so whatever else breaks, the words survive.
  - Mutation-verified: re-introducing the clear fails the guard.

## [0.9.100] — 2026-08-03
### Fixed
- **Every poll rebuilt the entire payload from scratch, so the board took six seconds to answer and a pasted image queued behind it looked like a hung upload.** The upload was never slow — a 3.7MB screenshot lands in 0.2s. `state.json` was the wall: `load_taskboard` alone spent 56 git subprocesses on L2 verdicts, and the roster, mail, archive and decisions were re-read alongside it, 1.5 seconds apart, forever. Each loader is now cached on the sources it actually reads — file mtimes plus git HEAD for the verdicts — so a poll recomputes only what moved. **7.9s → 33ms.** An unreadable source falls back to a 2s TTL, degrading to slow rather than to stale.
- **The answer goes to whoever WROTE the item, restoring the rule 0.9.99 broke.** An item the lead relays on a department's behalf answers to the lead, because it relayed the question and has to see the decision; preferring the department's own seat cut it out of a conversation it was carrying. A department that wrote to the board itself still gets its own seat, and an item with no recorded pane still falls back to its department.
### Added
- **An item says who wrote it** when that is not its department — a relayed item wears `via CEO`, so it is never mistaken for a direct one and the reply never seems to go to the wrong place.

## [0.9.99] — 2026-08-03
### Fixed
- **A department's answer went to the lead's input box while that department's own live seat sat there, resolvable.** Routing preferred the pane an item recorded at creation, and that pane is the LEAD's whenever a hook writes the item or the lead posts on a department's behalf. The department's own seat outranks it now; the recorded pane is the fallback, not the first choice. CEO and Boss items still address by pane, because they belong to the lead by definition.
- **The theme toggle was still a black blob in light mode.** The previous fix never applied: the replacement did not match, failed silently, and the check that was meant to prove it matched the `:hover` line instead of the rule. A test now scans the whole sheet for any dark chrome background sitting on a selector without `html.dark`, and it is mutation-verified against exactly this bug.
- **The sticky pointer outlived the ask it pointed at.** It only cleared on a redraw, so an item answered elsewhere left its pill on screen until the data happened to move.
### Changed
- **A pasted image uploads as bytes.** It went out as base64 inside JSON: the bytes grew by a third, then every one of them was escaped into a JSON string, sent, parsed back and decoded — four passes over several megabytes before one reached disk, which is why the confirmation took tens of seconds.

## [0.9.98] — 2026-08-03
### Changed
- **The accident guard's `rm -rf` whitelist covers every regenerable derived directory**, not `.next` alone: `node_modules` and `.cache` join it. A build cache holds no authored bytes, deleting one costs a rebuild and nothing else, and clearing it is the standard first move when a dev server misbehaves — so the guard was blocking the one destructive-looking command that destroys nothing. Every name on the list must be rebuildable from the repo alone.
- **The rule now applies per target, not per command.** It used to whitelist only a single-argument `rm -rf`, so clearing two caches in one line was blocked while clearing them one at a time was not. Every target must be whitelisted for the command to pass; one unrecognised path still stops it.

## [0.9.97] — 2026-08-03
### Fixed
- **The theme toggle rendered as a black blob in light mode.** Adding the sound switch inserted its rule before every occurrence of `#themetog {` — including the one inside `html.dark #themetog {`, which swallowed that selector and left the dark toggle's colours applying in both themes.
- **A white hairline in dark mode**, above the rail's *Show all*: its divider had no dark colour.
- **A cited FOLDER and an absolute path were not clickable** — which is to say the two forms a render is actually cited as. The matcher required a final `.ext`, so a path ending in `/` fell through as plain text; and the resolver refused absolute paths outright, which is where a pre-merge render lives (a dept worktree). Both are accepted now, both matchers move together, and the realpath pin still refuses anything outside the project and its linked worktrees. A directory is openable but never served as bytes.

## [0.9.96] — 2026-08-03
### Added
- **The page rings when something arrives.** The design carried two voices and the board shipped without either: a needs-you rings low and twice, an update is one soft high note, both synthesised rather than fetched. The server's banner covers a closed tab; this covers the case where they are looking at the page. A switch sits in the masthead and remembers itself. It rings for what ARRIVED — the first poll only seeds the set, so a reload never replays the backlog.
### Fixed
- **The toast no longer sits on the composer it reports about**, which is where it landed after a paste, covering the path it had just inserted.

## [0.9.95] — 2026-08-03
### Changed
- **A thread opens on its newest message and stays there.** It opened at the top, so every visit began with a scroll down through history to reach the thing that just arrived. It now lands on the newest on first render, and a message arriving while they are already at the bottom keeps their there — the stick-to-bottom every chat client has. Scrolled up to read, their position is held instead: yanking their away mid-sentence is worse than a missed jump.
- **The conversation frame never goes below 600px.** The floor was 420, which on a short window left a thread barely two messages tall.

## [0.9.94] — 2026-08-03
### Added
- **The composer takes a pasted image.** It was text-only, so an item that needed a screenshot to answer could not be answered from the board at all — the reply had to be typed into the terminal instead, which is the one thing the board exists to avoid. A pasted image is written into the project (`docs/board/pastes/<stamp>-<item>.<ext>`) and its path is inserted at the caret, because a path is the one form of an image the session on the other end can open.
  - The endpoint stays a narrow door: `data:` URLs only, the four clipboard image types only, 12MB cap, and the filename is generated rather than taken from the page — a client-supplied name is the one field that could climb out of the directory.

## [0.9.93] — 2026-08-03
### Fixed
- **The conversation rail's age froze.** `11m` stayed `11m` twelve minutes later. Every age on the page is derived at render, and the panel redraws only when the DATA changes — which on a quiet board is never — so one pass, `retick()`, re-derives them once per poll from a `data-ts` the markup carries. The rail printed its age as bare text with no `data-ts`, so it was invisible to the only thing that keeps a clock honest. This is 0.9.83's fault re-entering through a lane written after it: the mechanism was right and the new markup did not opt in.
  - Four tests now guard it, including one that scans the conversation layer for any age rendered without a `data-ts` — a lane added later cannot forget it silently.

## [0.9.92] — 2026-08-03
### Fixed
- **The composer was being destroyed and rebuilt under their hands, every 1.5 seconds.** The persistent composer draws from `renderTray()`, which runs on every poll, and it rewrote its own `innerHTML` unconditionally — so the textarea was replaced on a timer while the Boss typed into it. With an IME that is destructive rather than merely rude: the uncommitted composition lives in the element, so replacing it mid-word threw the composition away and left the raw pinyin behind (「很」 arrived as `hen`).
  - **It rebuilds only when something about it actually changed** — bound item, conversation, staged count, delivery target — and never at all while an IME composition is open. A commit or a Reply/Ask click still forces a rebuild, because those are the moments the box must change.
### Changed
- **The masthead stamp reads `last change`, not `updated`.** Since 0.9.83 it has named the moment the content last changed, deliberately, so that the one clock on the page could not claim a freshness it did not have. But `updated` reads as "last refreshed", so a correct stamp on a quiet board looks like a frozen one. The tooltip still carries the last poll.

## [0.9.91] — 2026-08-03
### Changed
- **Whatever happens, the answer lands on the clipboard.** It was copied only on failure; a send that half-lands is exactly when the text is needed, and the basket is flushed by then, so the clipboard is the only remaining copy of what was written. It is copied first now, before any branch, and every outcome says so.
- **`@BOSS-DONE` no longer follows an answer.** The Boss replying resolves the item server-side as they send it, so a DONE on top closes what is already closed — a turn spent on a no-op. Three documents still instructed it; the marker keeps its real job, which is retiring an ask the raiser itself is withdrawing, or closing the old one when re-raising a revision.

## [0.9.90] — 2026-08-03
### Fixed
- **A department's seat is resolved by the card it holds, not by which one moved last.** 0.9.89 routed a department's answer to its most recently active seat, which is a guess dressed as a rule: two seats of one department are routinely live at the same time — one waiting on the lead, one waiting on the Boss — and "whoever moved last" cannot tell them apart. A teammate is dispatched per card and named for it (`Frontend-988` holds `#988`), and the board entry already records its card, so the seat is an identity and not a ranking.
  - The seat named for the item's card wins outright. Failing that, a department with exactly one live seat is unambiguous.
  - **More than one live seat and no card match is refused, and says which seats it found.** Delivering a decision to the wrong desk is worse than not delivering it; the answer is copied instead, and nothing is typed anywhere.

## [0.9.89] — 2026-08-03
### Fixed
- **An answer to a department was typed into the lead's input box instead of that department's session.** Origin routing keyed on the pane an item was written from, and a teammate writes to the board from a process that carries no `ITERM_SESSION_ID` — so its items recorded no pane at all and fell through to "the board's default seat", which is the lead. Technically the documented fallback, and useless: the department that asked has its own live session, and the session registry has known where it is all along.
  - **A group with no pane is now keyed by DEPARTMENT**, and the send path resolves it to that department's most recently active live seat. Two seats can be live at once, one per card; the newest wins, because that is the one still working.
  - A department with no live seat still falls through to the default, so nothing that used to arrive stops arriving.

## [0.9.88] — 2026-08-03
### Added
- **The four priorities have names, and a bug wears its own tag.** `P0 urgent · P1 critical · P2 important · P3 nice-to-have` — the words are the whole definition; which level a card gets is a judgment, and the judgment stays with the CEO rather than being encoded as a rubric. A card can be a bug at any level, so `kind: bug` is a separate tag beside the priority instead of a fifth level competing with them.

## [0.9.87] — 2026-08-03
### Fixed
- **The read mark sits outside the bubble, beside it, level with its bottom edge.** It had been beside the id, then at the end of the header row, then inside the bubble — three placements, none of them the one that was asked for. The bubble and the mark are now a flex line, so the mark is the bubble's sibling rather than anything nested in it.

## [0.9.86] — 2026-08-03
### Added
- **Every priority level renders.** `P2` and `P3` sorted correctly and drew nothing, so a board carrying 22 cards at those levels showed a tag the page never displayed. All four now wear a pill on a single ramp — P0 deepest, P3 coolest — instead of only the top two.
### Changed
- **The masthead is one line.** `BOSS BOARD · <project>` rather than the product's own name stacked above the project's, with the band's padding cut; it was spending a third of the page's height on chrome.
- **Stage and Send are one group.** Two competing auto margins — one on the hint, one the composer's Send inherited from the tray — split the free space and parked Stage in the middle of the row.
- **The read mark rides the bubble**, bottom-right, where a chat client stamps a receipt. Beside the id it read as part of the id; at the end of the header row it floated away from the message it belonged to.

## [0.9.85] — 2026-08-03
### Fixed
- **A sent answer stayed sitting in the composer.** Staging cleared the draft and unbound the target, then the redraw copied the text straight back out of the live element, so the box looked as though nothing had been sent. The composer now keeps a draft per binding and forgets which binding the element belonged to the moment its text is consumed.
- **Stage came back.** The persistent composer shipped with Send alone, which lost the ability to hold several answers and flush them together. Stage sits beside Send (`⇧⌘↩` and `⌘↩`), and both run one path, so a staged answer and a sent one are the same object.
### Changed
- **The message is the answers, with no preamble.** It used to lead with a count of what was being sent and an instruction not to re-run the done-marker — bookkeeping about the message rather than the message, arriving in front of every answer written.

## [0.9.84] — 2026-08-03
### Added
- **The Boss Board dashboard is a message list.** The desk was a mail-style feed: one undifferentiated column where forty-five updates and the one decision that mattered read at the same weight, and the department that raised an item was invisible until the row was expanded. It is now a chat client. One conversation per department; a rail split into the ones needing a decision and the ones with unread updates, each with an unread count and the last line said; a thread of dated messages with clock times and day dividers; and one composer pinned to the bottom, addressed to the conversation it will reach.
  - **An ask carries its state on its face.** `needs you` until it is answered, `answered` after, with a coloured rail either way — a resolved decision no longer disguises itself as an update. Reply exists only on an ask, because only something that asked a question can be resolved by an answer; an update offers Ask and Archive.
  - **Answers quote the ask they settled**, id and opening line, clickable back to the original. A reply that floats free of its question is unreadable a day later.
  - **An unanswered ask that scrolls out of view leaves a sticky pointer** at the top or bottom of the thread; clicking it scrolls there and flashes the message.
  - **A conversation with nothing unread is off the rail.** Reading is filing, so a quiet department appears only behind `Show all`.
- **An answer is delivered to the session that raised its item.** Every entry now records the pane it was written from, and a Send groups the staged answers by origin and delivers one message per session. Nothing has to infer which session is which any more; a mixed batch goes to two places and each half goes home.
- **macOS notifications on arrival.** Sender first, the way a chat client writes one: the department is the title, the item's subject the subtitle, the detail the body. Two voices — a low double chime for a decision, one soft note for an update — plus the board's own icon, a click that opens the board, and one banner per item rather than a stack. Requires `terminal-notifier`; without it the board is silent and everything else works.

### Fixed
- **Send can now press Return.** It typed the answer into the pane and stopped, on the belief that a background process cannot submit; it can. The answer is typed, then a lone carriage return follows as its own write, which is indistinguishable from the keystroke.
  - **Four checks stand between a staged answer and that keystroke**, because the failure it buys is a sentence executed in the wrong place: the pane still exists, its terminal has a foreground `claude` (checked *before* anything is typed), the pane's own screen changed afterwards, and the change is the text that was sent. Any check that cannot be passed stops at "typed" and leaves the Return alone.
  - **A pane that is no longer a live session is refused outright** — nothing is typed into it at all.
- **A branch office could take the main session's delivery target.** It runs as its own top-level session out of a worktree and carries none of the marks a teammate does, so the guard waved it through and the last session to finish a turn owned the pane. The seat is claimed now, not last-writer-wins: a branch can never hold it, a live holder keeps it, and a target auto-claimed onto anything else refuses to deliver.
- **Reading an update no longer sends a read receipt.** It applies at the click and tells nobody; the board used to append `Read: <ids>` and a note announcing that no action was wanted.
- **Sessions are indexed by id and labelled with the last thing typed into them**, so a delivery target is named in words rather than by a pane title Claude Code rewrites per task.

### Changed
- Tabs wear an underline instead of a pill, and the strip no longer parks a scrollbar next to the last tab. A filed message keeps its colour and wears a tick, rather than greying into something harder to read than an unread one.
- 557 tests (up from 545), covering the delivery interlock, the seat rules, origin routing and the session index.

## [0.9.83] — 2026-07-31
### Fixed
- **Every clock on the board was wrong, in both directions at once: the masthead reprinted the wall clock on every poll, and every age on the page froze between data changes.** Their report: the numbers keep moving, the time does not. Both halves are the same design fault seen from opposite ends. The panel redraws ONLY when the payload changes — deliberately, because a rebuild every 1.5s would collapse whatever they had expanded and destroy the reply box they was typing into. But every time on the page is an age *derived at render* (`7h`, `now`, `3d`, `last answered 14m ago`, `2h in 审查`), so on a quiet board they all stopped at the last change and stayed there, while the one line that did update — `updated <HH:MM:SS>` — was not reading the data at all: it printed `new Date()` on every poll, so it claimed freshness forty times a minute on a board where nothing had moved since breakfast. The net effect is a page that looks live and reads stale, which is worse than either one alone: the clock they can see moving is the one with nothing behind it.
  - **Ages now re-derive in place, once per poll.** Each drawn age carries its own timestamp (`data-ts`, or `data-since` for the minute-precision time-in-stage chips), and one pass rewrites the text nodes without touching the DOM around them — so expansions, scroll position and a half-typed answer all survive a tick that moves `59m` to `1h`.
  - **The masthead stamp now names the moment the CONTENT last changed**, not the moment it last checked. A quiet morning reads `updated 08:12:04` and means it. The poll that proves the page is still live moved to the tooltip, and a server that has actually died still announces itself the way it always did, by dimming the page and replacing the line outright.
### Changed
- **Needs-you reads newest-first** (their ruling). It drained oldest-first on the theory that nothing should sink — but the Boss reads the top of the desk, so the ask they had just watched a department raise was landing at the bottom of the lane. Age is on every row, so what has waited longest still says so out loud. Information already read newest-first and is unchanged; Parked keeps queue order, because that lane *is* the backlog and it drains from the front.
- 651 tests (up from 645). The desk's ordering rule is now exercised through the panel's own `tick()` rather than a copy of the sort, and all six parts are mutation-verified.

## [0.9.82] — 2026-07-29
### Fixed
- **The version record described the process that spawned the server, not the server — so "a new window on every update" came back.** 0.9.78 made replacement monotonic and stopped a replacement from opening a tab; this is the same symptom re-entering from the other end. `ensure_server` stamped the record with `BUILD`, which is computed once when the module is imported. That is right for a running daemon — it *is* the code it executes — and wrong for anything that spawns one, because the spawn re-execs the file: the child runs whatever is on disk now, while the record named the parent's in-memory copy.
  - **Long-lived importers make that gap unbounded.** The board's MCP channel holds the module in memory for days, straight through every plugin update, so its stamp ages while the code it spawns stays current. Caught in the field: the record read a build that existed nowhere on disk, against a server running the newest code.
  - **A stale stamp always reads as OLD, which grants every other install a licence to replace.** Each replacement leaves a window with nothing listening, and any call landing in that window sees no server, reports that it started one, and opens a browser window. The churn is self-sustaining: the next spawn by the same fossil re-poisons the record.
  - The record now carries the stamp read fresh from disk — the code actually being exec'd — so it cannot lie, and the same fresh stamp decides whether to replace. That second half matters on its own: judging with a fossil makes an install decline to retire a genuinely stale server, which is how an updated plugin ends up serving the old panel out of a daemon's memory. An unreadable file falls back to the in-memory stamp rather than recording an empty version, which would read as older than everything.
- 645 tests (up from 641). All three parts are mutation-verified, including a three-build case (fossil parent < stale server < on-disk) that the first pass of tests did not distinguish.

## [0.9.81] — 2026-07-29
### Fixed
- **The read tick vanished its own row, and asking about an update did not count as reading it.** Two halves of one wrong model in the desk's Information feed. Ticking `read` folded the item to History the instant the box was clicked: the row disappeared under its own tick — which reads as the item being lost, and leaves nothing to untick — while the acknowledgement it staged still needed a Send of its own to flush. And staging a question on an update left the item sitting unread, so the natural flow (ask about it, send) ended with a manual tick plus a second Send just for the ack. The staging model the rest of the desk already uses now covers both. A tick stages: the row dims in place, ticked, and folds to History at Send with the rest of the batch — unticking before Send works, and unticking an already-folded item still lifts it back out of History. An ask on an Information item marks it read at send — asking about an update *is* reading it. A staged question pins the tick (checked, disabled) rather than letting a stray click overwrite the question in the one-answer-per-item basket.
### Changed
- The "Information ≠ decisions" predicate is one named server-side function shared by the desk mirror and the send path, with the panel's `isInfo()` as its declared JS twin — a third divergent copy of a rule is exactly how a field-shape change breaks silently.
- 641 tests (up from 636). The stage-not-fold tick and the ask-folds-at-send rule are mutation-verified.

## [0.9.80] — 2026-07-29
### Added
- **The lead now sees every seat's context gauge — the number nobody could watch.** Teammates were grinding until passive auto-compact and the work degraded: a seat cannot see its own context percentage, the per-pane statusline is visible only to a human who cannot watch four panes at once, and the doctrine ("ask for a manual /compact when bloated") had no mechanical backstop — its violation announced itself only as the auto-compact it existed to prevent, after quality had already decayed (a bloated seat re-proposes its own abandoned approaches, and the compact summary is lossy on top). A new lead-session sentinel reads each live teammate's transcript and computes real usage from the last API call's `usage` fields — never a statusline estimate, which has been caught claiming 90% when the true figure was 51%. At 50% of the model's window it says give the next card a fresh seat; at 70% it says rotate at the current card's boundary — checkpoint (commit WIP + a handover file: state, tried-and-abandoned approaches, next step), retire, spawn fresh, so a rotation inherits the distilled reasoning instead of throwing it away. One nudge per seat per threshold; the record follows decreases silently, so a respawned seat under the same handle earns its own future nudges. The Registrar is exempt (mechanical proxy, nothing of quality to lose). Thresholds and per-model windows are overridable in `orchestrate.json` (`seat_ctx_warn`, `seat_ctx_high`, `context_windows`).
### Fixed
- **The seat-accumulation counter never fired for the one pattern it existed to catch.** It flagged a seat that had closed `seat_cards_max` cards only "between cards" — polite in intent, but a queue-fed seat never *has* a between-cards moment, so a seat could close four cards and hold two more in progress without a word (field case, 2026-07-29). A busy over-limit seat is now told the card in hand is its LAST — queue nothing more onto it, rotate at the boundary; an idle one keeps the retire-now message, and the two states re-arm each other. A fat seat is also no longer simultaneously offered new work by the idle-desk check — a contradiction the lead used to resolve by feeding the seat, which is the accumulation loop again. The test that asserted the old behaviour is corrected rather than deleted.
### Changed
- Teammate lifecycle doctrine: mid-task bloat now prescribes rotation at the card boundary with a handover file, not a manual /compact that depended on a human noticing in time; the "hand the next card to the live teammate" zero-idle exception is bounded by the context warn threshold and the seat-cards cap — that exception was exactly how seats accumulated forever.
- 636 tests (up from 623). The busy-seat unmute, the nudge ratchet and the usage summation are each mutation-verified.

## [0.9.79] — 2026-07-28
### Fixed
- **A non-ASCII task name silently voided the whole board marker.** The task segment of `@BOSS[<dept>#<task>]` accepted ASCII only, so a marker naming its work in Chinese matched nothing, landed in the malformed-marker log and nowhere else. That is worse than the silence the register exists to prevent: the model had just been *nudged* into registering the ask, complied, and the ask still never reached the panel — twice, in the field. The segment now takes any run that is not a bracket, whitespace or `#`; genuinely malformed markers are still recorded as misses.
### Changed
- **The unmarked-ask nudge no longer fires inside a branch office.** It is a CEO-team piece: it exists because a prose-only ask dies in a scrollback that cannot be reliably scrolled back through, and because the panel then shows nothing waiting. A branch runs as its own session against a handful of desks with the Boss working inside it directly, so the register it defends is the conversation they are already reading — firing there interrupts a turn to demand a board entry for a question they have just been asked to them face. It now uses the same branch gate as the other CEO-team sentinels; a branch that wants it can opt back in with `board_nudge: true` in its office file.
- 623 tests (up from 614). Both changes are mutation-verified.

## [0.9.78] — 2026-07-28
### Fixed
- **Two installs were killing each other's panel server, which is why the open tab kept dying and why every update opened a new one.** The plugin runs from a *versioned* cache directory, so a long-running session pins an old copy while a newer one sits alongside it. Both call the same "make sure the server is up" routine. The rule was *replace whenever the recorded build stamp is not mine* — so each read the other as stale and killed the other's server on every single call.
  - **The refused connection.** The port is dead between each kill and each bind. A tab polling across that window recovers, but a reload lands on nothing, and if the losing side happened to swap last the server could stay down entirely.
  - **The new tab every time.** The routine reports whether it started the server, and the caller opens a browser window when it did. Under a permanent replacement loop that was *every* call.
  - The state that produced it: four cache directories alive at once, two of them holding byte-identical code but different plugin versions — the stamp carries the version of the directory a copy happens to sit in, so identical behaviour still disagreed about who was current.
  - **Replacement is now monotonic:** only a strictly newer build replaces a running server; an older one reuses it. At most one of any two builds can replace the other, which is the property that makes the loop terminate. The behaviour the stamp exists for is intact — an updated plugin still will not keep serving the old panel out of a daemon's memory, and an edited working copy still self-deploys without a version bump.
  - **Started now means "there was nothing running"**, the only case where a browser window is actually needed. Replacing a live server leaves the tab where it is; the page already reloads itself as soon as the server answers with a new version.
  - A server that has just been replaced will not be replaced again for a short window, as a backstop against any cause the ordering cannot rank.
- 614 tests (up from 606). The monotonic rule, the tab rule and the backstop are each mutation-verified, and the test that asserted the old behaviour is corrected rather than deleted.

## [0.9.77] — 2026-07-28
### Fixed
- **The Canon panel was reading the wrong half of the file, and had been all along.** The canonical-answers registry is a Markdown table, written and read by the canon tool. The panel never used that parser: it ran a bullet regex of its own, which matches nothing in the table and everything in the `⚠ needs re-check` list printed above it. So the panel titled "settled answers" was in fact listing the entries that were **not** settled, and its count was the size of the re-check queue.
  - The failure only became visible when a project rebuilt its registry and cleared every flag: the panel dropped to zero, which reads as the canon vanishing when it is the opposite — the registry was healthy and nothing needed re-checking. Verified against the file's history, where the panel's count tracked the flag list row for row and never once matched the registry.
  - The panel now reads the registry with the canon tool's **own** parser. One reader, so a change to the file's shape cannot teach one half of the system and not the other — which is what happened here, and the seventh instance of that fault this week.
  - A registry row is a question and the file that answers it, so it now shows both, plus the owning department and the date. Needing re-check is a **flag on the row** and a separate count in the header, never the panel's whole content.
- 606 tests (up from 602), including the field case, and the old regex is mutation-verified to fail them.

## [0.9.76] — 2026-07-28
### Changed
- **The reply box moved into the row it answers.** It was a bar fixed to the foot of the window: a *chat* composer, which is the right shape for one conversation and the wrong shape for replying to one item in a list. Anchored to the window rather than to its own subject, it sat on top of the very row it belonged to — the previous release papered over that by quoting the ask back inside the box — it needed the page's bottom padding measured to it so it would not bury the last rows, and under browser zoom it stranded itself away from the item entirely, since a fixed element does not travel with the magnified content.
  - **In the row it is ordinary.** It opens underneath the ask, pushes the list down, and scrolls with the page. It cannot be separated from the question, because the question is the line above it. The quote line, the panel stacking, the measured page padding and the entry lookup that fed the quote are all gone with it.
  - The row being answered is forced open, so the box never hangs off an item whose text is clamped mid-sentence, and clicks inside the box no longer fold the row away.
### Fixed
- **A draft could be filed against the wrong item.** Drafts were keyed on whichever item was *currently* targeted, but the redraw that follows a switch reads the textarea *before* replacing it — so clicking Reply on a second ask attributed the first ask's half-written answer to the second one. Worse than losing it. The box now carries the id it was rendered for, and the draft is keyed on that.
- Typing survives a redraw: the box is part of the list, so any board change under their hands rebuilds the element being typed into. Text and caret are captured and restored.
- An in-flight edit of an already-staged answer is no longer reverted by a redraw. The previous rule discarded any draft whose item was in the basket, which is exactly the case where an edit is in progress.
- A load-time crash: the keyboard hint was declared in one place and initialised in another, leaving every earlier reference in the temporal dead zone. It threw on load and took the rest of the panel with it.
- 602 tests (up from 598). The draft-leak, the redraw capture and the click guard are each mutation-verified.

## [0.9.75] — 2026-07-28
### Changed
- **The reply box, refined.** It is the one place on the board where work is *produced* rather than read, and it was the least considered surface on the page.
  - **It quotes the ask it is answering.** The composer is a fixed panel at the foot of the page, so it sits on top of the row it belongs to — you were being asked to type from memory into a box covering the question. The title now appears above the field, clamped to two lines; the detail stays in the row where it belongs.
  - **A draft is no longer destroyed by cancelling**, nor by clicking Reply on a different item. Unstaged text is kept per item and restored when you come back to it, and consumed once it is staged so it cannot shadow a later edit.
  - **Keyboard.** `⌘↵` stages, `⇧⌘↵` stages and delivers, `Escape` closes. Escape closes one thing, innermost first, so a half-written answer is not dismissed by the key press meant for a card modal behind it. The hint names the modifier the reader's own keyboard actually has.
  - **The staged batch stays visible while you write.** It used to hide behind the composer and reappear only after it closed, which is why the send control seemed to come and go; the two panels now stack.
  - **Delivery is one step from the box.** Sending flushes everything staged, not just the item in front of you, so the button says the real number.
  - The field starts at one line and grows with the answer, and the page reserves the panel's *measured* height rather than a fixed guess — the composer's height varies with the ask it quotes.
- 598 tests (up from 589), including the composer's draft guarantee, verified by mutation.

## [0.9.74] — 2026-07-28
### Fixed
- **Two repetition faults the new lane view made visible.**
  - A lane row ended with the name of the lane it was already in. The age helper appends *where* a card sits, which earns its place in the mixed card grid and is pure noise once the list is filtered on that stage; lane rows now show the age alone.
  - A card store writes a placeholder dash for "no department" as readily as it writes nothing, but only the empty string was treated as unassigned — so a placeholder drew a coloured chip naming a department called "—". Both now read as unassigned.
- 589 tests (up from 587).

## [0.9.73] — 2026-07-28
### Changed
- **The dashboard is an inbox now: a rail of counts beside one list, replacing three columns and a four-tile monitor.** The old grid was measured against a live board at 1440px wide and failed three ways at once. The columns were independent, so the tallest set the page height and the other two simply stopped: the ordinary state of nothing to answer against a full feed of notices drew two screens of blank canvas next to a narrow ribbon of text, using about a third of the available width. Importance was encoded in a small coloured dot and a column position, but *size* is what the eye reads, and size was driven by item count — so notices out-shouted the one thing that needed a decision by an order of magnitude. And the first thing on the page was four large numbers, three of them usually zero, above a block of standing doctrine that changes perhaps monthly.
  - **One list cannot have an empty column.** Rows collapse to a single line, with the identifier, the department and the kind — three fields already carried by the dot and the lane — behind the click rather than repeated on every row.
  - **A live ask is visibly different in kind, not just in position:** a wider row, a heading-sized title, an accent rule down its edge, and its actions on screen without a hover. It is the one row that is meant to be acted on.
  - **With nothing waiting, the desk shrinks to a single line** rather than padding itself out with status. An empty board should get smaller, not look busy.
  - **The rail carries every count that used to cost a tab switch** and doubles as the filter: waiting, unread, parked, history, in-progress lanes, and what shipped today.
  - The standing-context band is collapsed to one line, expanding on click; it was pushing the first actionable thing below the fold on every visit.
  - `?desk=<lane>` opens straight onto one lane, the same way the existing tab and card deep links work.
### Fixed
- **The board answered "how much work is live" twice, differently, on the same screen** — one figure counted two lanes, the other counted the fuller definition in which a card that has passed review is still in flight until it merges. Both were defensible; having both visible was not. The rail's lanes are now a *partition* of the header's figure: disjoint, and summing to it exactly. Notably, a card that has passed review is usually still filed as not-started, so it appeared in the backlog count as well; it now appears in exactly one lane.
- **Three live entry kinds had no dot colour and rendered an invisible marker.** The rule was to give every kind a colour, which failed silently as kinds accumulated. The base element now carries a colour in both themes, so an unlisted kind degrades to a neutral dot instead of a blank. A default cannot rot the way an enumeration does.
### Added
- **The panel's own JavaScript is now under test**, executed under node against a stubbed DOM rather than matched as text. Every display fault this month was a rule that nothing could verify. The lane rule is a single named function that the renderer and the tests both call, so a test cannot pass against a copy while the board drifts underneath — verified by mutation.
- 587 tests (up from 572).

## [0.9.72] — 2026-07-28
### Added
- **Review evidence is now bound to the change it judged, not to a clock.** A verdict's subject is a CHANGE, so keying its validity on timestamps was the root of a whole class of faults: `since` re-stamps on every status edit, which made the board's own upkeep destructive.
  - **The 审查官 records what it judged** — `sha:` and `patch-id:` inside the marker it writes. A patch-id is stable across rebase and cherry-pick, so it proves the change that passed is still the change on offer.
  - **Evidence outranks the clock.** A marker naming a patch-id still present in the repository counts whatever the timestamps say; one naming a change the repository does not have is refused, which is *stricter* than the clock rule and for a better reason. Markers with no evidence fall back to the clock rule, so every verdict written before today keeps working — that fallback is the common path, not the exception.
  - **Memoised, because the panel polls.** A commit's patch-id never changes and is cached permanently; the repository scan, needed only when a reviewed commit has been rewritten, costs about a second and is cached for a minute. `_attach_l2` runs per card, and the panel refreshes every 1.5 seconds.
- 572 tests (up from 560).

## [0.9.71] — 2026-07-28
### Fixed
- **Making the board more accurate destroyed real review verdicts.** A card was refused completion because its marker was "older than the card's current stage" — by nine minutes. The review was genuine; what moved was the card file, because the stage clock re-stamps on every status change, so recording `blocked_on` after a pass invalidated the pass. The session that hit it named the shape exactly: state inferred from a moving proxy rather than from the evidence.
  - **The tolerance now matches what the test is actually asking.** It rejects two things: a marker from a different card that held this platform id in an earlier session, and a pass from an earlier leg of this card since re-dispatched. Both are *days* out — the field cases were 5 to 8 days. Five minutes was calibrated for `since` being minute-precision, not for a clock that moves whenever the board is tidied. One day separates the two populations without softening the test.
  - **The gate stopped carrying its own copy of the rule.** It had one, added a day earlier, and that is why widening the rule did not reach it. It now calls `board.l2_verdict` and derives only the *reason* for a refusal, so "no review happened" and "the review is not about this leg" stay distinguishable in the message.
  - Corrected an assertion of my own from the day before: a card number is a permanent *identity*, but not permanent *freshness*. It is exempt from the date test only when there is no clock to check against, never in general.
- 560 tests (up from 555).

## [0.9.70] — 2026-07-28
### Fixed
- **The stall alarm's "awaiting merge" count was mostly false: 35 cards where the panel confirmed 9.** A session refused to trust the alarm and derived the answer from git instead, which was the right call. Two independent defects, both the same disease as the week's other faults: one rule, several readers, the fix reaching only some of them.
  - **No date test at all.** The panel has compared a marker's date against the card's stage clock since 0.9.61, and the completion gate learned it in 0.9.68; the alarm never did, so every recycled task id attached an old verdict to whatever card holds that number now. The rule now lives once, as `board.l2_verdict`, and both readers call it. The alarm and the panel are now checked for parity by a test, which is the check that would have caught this.
  - **Not every numbered file in the board folder is a card.** A plan of record and a schema proposal live there too. With no frontmatter they parsed as cards with no status and no stage clock, so a durable-id marker match went unchecked and they sat in the queue as awaiting-merge permanently. The card store already refuses to guess at a non-card; the alarm was the only reader that did, and now uses the store instead of a glob. Four such files were being counted on a live board.
  - **The row's advice no longer assumes the merge is still owed.** Much of that queue is work already on master whose card was never completed, so the action is often completion alone.
- **The stall alarm had no tests.** It has twelve now, including the panel-parity check and the two field cases above.
- 555 tests (up from 543).

## [0.9.69] — 2026-07-27
### Fixed
- **CEO-only sentinels were firing into teammates' panes, and the instructions in them are dangerous to obey.** A dept pane ended a turn and printed the lead's stall report, a merge backlog, and prompts to respawn agents. None of it is a department's business, and "a department never merges to master" is a hard rule that only has to be obeyed once by a tired agent to break.
  - **The event is not the gate.** The capacity check tried, by only running on `Stop` — but a teammate finishing a turn *is* a Stop in its own session, so the test excluded nobody, while its own opening comment claimed "lead session only". The stall check had no test at all.
  - **The fix that was already there had only reached half the problem.** Both sentinels carried the 分公司 exclusion added the day before, so the report that prompted it was cured while internal teammates kept receiving everything. One job, several implementations, the fix landing on only some of them — the same shape as three other faults this week, this time in the tooling itself.
  - **One helper, `hooklib.is_lead`, and deliberately not a second one.** Session startup already told the lead from a teammate reliably: a teammate's transcript stamps its agent name on every line. That reader now lives in `hooklib` (it used to sit inside a Stop piece, which is exactly why the sentinels that needed it never got it), the Boss-Board nudge drops its own copy, and **unknown reads as LEAD on purpose** — the lead's transcript is the one with no stamp, so treating absence as doubt would silence every sentinel for the one session that exists to receive them. A 分公司 carries no stamp either, so it keeps its own mail nudge.
  - **Five pieces gated, not the two reported.** The stall, capacity, task-reconcile, mail and board-pointer checks. The pointer was mine, shipped hours earlier with the same defect, and worse than noise: its state is shared, so a teammate ending a turn first would mark an arrival as announced and the founder would never see it.
- 543 tests (up from 532).

## [0.9.68] — 2026-07-27
### Fixed
- **A recycled task id could open the completion gate on another card's review.** Platform task ids restart every session, so a `.pass` written weeks ago attaches to whatever card holds that number now — a card its reviewer never saw. The board learned this in 0.9.61 and started comparing a marker's date against the card's stage clock; the gate never did, and 0.9.67 widened what it could see without adding the same test.
  - **The gate now reads the board's own marker rules** (`_review_markers` · `_stage_ts` · `STAGE_GRACE`) rather than deriving its own. A gate that disagreed with the panel would show 已过审 on a card it then refused to let through.
  - **A durable `#NNN` needs no date proof; a task id does.** The card number is a permanent identity and cannot collide with another card's review. The five-minute grace absorbs `since` being minute-precision, exactly as the panel's does.
  - **Deliberate asymmetry with the panel, recorded as a choice:** with no clock to compare against, the panel refuses a task-id match while the gate allows it. A missing chip costs nothing; a false refusal blocks finished work, and a project running without cards has no clock at all.
  - **Its refusal now says which of the two failures happened** — no marker, or a marker belonging to an earlier leg. A gate that reports "no pass" while a pass file sits on disk is how a real verdict gets mistaken for a plumbing bug.
- 532 tests (up from 526).

## [0.9.67] — 2026-07-27
### Fixed
- **Real review passes were invisible, so finished work could not be ticked off.** The Auditor's own spec asks for two different filenames: `<id>.pass` on a pass, but `<dept>.<id>.<n>.fail` on a bounce. Writing both from one seat, reviewers settled on the dept-prefixed form for passes too, and the field filled with `Ops.409-checkout-price.1.pass`. Every reader assumed the bare form, so verdicts that genuinely existed on disk could not be seen by the completion gate, by the board's L2 chips, or by the stall sentinel. The CEO hitting this refused to write the marker itself, which is exactly right: a producer signing its own review is what the gate exists to prevent.
  - **One parser, `board.review_key`, replaces three divergent copies.** The id is the first dot-segment beginning with a number (the trailing segment is the attempt count and would otherwise win), `x<NNN>` is an external card's key, a dept handle carrying digits is skipped because the segment must *start* with the number, and a marker with no numeric segment falls back to the old rule so nothing that worked before breaks. `.archived` returns nothing at any call site: a retired verdict must never reopen a gate.
  - **The gate now accepts either id.** Platform task ids restart per session while the durable card number does not, so a marker keyed on either is the same verdict. The board has matched both since 0.9.58; the gate had not caught up. Its refusal message now names both accepted shapes and says plainly not to self-sign.
- **Completed cards vanished instead of landing in Done.** The digest is regenerated from the *active* card directory, so the moment a finished card is retired to `<board>/done/` it left the digest and the pipeline showed nothing where it had been. Retired cards are now read back as done tasks, newest first and capped at 25: Done is the tail of the pipeline, and the archive is where the full history belongs. Each keeps its date, dept, branch badge and task id, so the today-versus-earlier split still works.
- 526 tests (up from 492).

## [0.9.66] — 2026-07-27
### Fixed
- **One marker immunised a whole turn, so a second ask left in prose was never caught.** Found from a live screenshot: a session that had raised its escalations to the board also ended on a design question that existed only in the terminal, and the panel showed nothing waiting for it. The unmarked-trailing-ask nudge asked "did this turn register anything", when the question it needed to ask was **"is THIS the thing it registered"**. It now compares the trailing ask against what was actually raised, by content-word overlap, and a turn that registered nothing keeps the original behaviour untouched.
  - **CJK is tokenised as unigrams, deliberately.** Bigrams look more precise and are worse: one inserted particle shifts every pair after it, so two phrasings of the same ask scored 0.38 and read as unrelated.
  - **A one-word closer never second-guesses a turn that registered something** — too little to compare, and the benefit of the doubt belongs to the turn that did the right thing.
  - **The nudge text now carries the point-do-not-repeat rule.** A running session never re-reads a skill file, so the hook is the only channel into one; doctrine that only lives in a document cannot reach the sessions already in flight.
- 492 tests (up from 478).

## [0.9.65] — 2026-07-27
### Added
- **The board is now a destination with a doorbell.** A terminal transcript is a stream: founder-facing items arrive interleaved with progress, and new output destroys scroll position, so anything that must be re-read is lost. The board was the answer to that and was under-used, for two reasons only one of which was the channel.
  - **An MCP server ships with the plugin** (`.mcp.json` at plugin root, started automatically): `mcp__boss__message` · `resolve` · `list_open`. Items used to reach the board only as `@BOSS[…]` markers parsed out of assistant text at turn end, which is fire-and-forget: a missed parse loses the item in silence, and nobody learns the message never arrived. A tool call **returns a receipt**, so a rejected post is visible; it **works from a subagent session** without depending on that session's Stop dispatcher; and its arguments can be **validated**, which is the only real noise filter, since prose cannot be checked and a schema can. `kind` comes from a closed set (`decision` · `blocker` · `signoff` · `info`), `ask` is one line capped at 200 chars, `detail` is capped and refused when it merely repeats the ask, and every rejection **teaches the shape** rather than saying "invalid". Pure stdlib JSON-RPC over stdio, stdout kept protocol-only, every handler wrapped so a tool error can never take the server down.
  - **The refined kinds are additive.** The store's split is binary (anything not `info` files under Needs-you), so the new kinds need no migration, give the display something meaningful to group by, and each ships with its dot colour in both themes: an unstyled kind renders as an invisible dot, which is the kind of thing that ships broken.
  - **`stop_board_pointer`: one reading, two surfaces.** The real reason the board went unread was that nothing announced a post, so they stayed in the terminal, and because that is where they was, agents kept writing there. Now a turn end that finds new items fires **one desktop banner** carrying the first ask, and prints **one terminal line**: how many wait, the oldest age, a breakdown by kind. The line points and never carries content, which is the one thing a stream is good at. State lives in the main checkout so several sessions on one board cannot each announce the same arrival, and the signature carries the id set **and** an age bucket, so a board nobody clears re-speaks as it ages instead of going quiet forever. The banner fires only on arrival: a banner saying "still 2 waiting" is nagging.
  - **Doctrine: point, do not repeat.** Once an item is on the board, the reply says where it is rather than restating it. Progress belongs in the terminal, decisions and sign-offs and blockers and durable facts belong on the board.
- 478 tests (up from 432).

### Deliberately not built
- A second enforcement sentinel over the same facts. An unmarked trailing question is already blocked once by the ask nudge, and cards nobody advances are already surfaced by the stage-stall sentinel; a third pass over the same state would be noise wearing the costume of rigour.
- Phone push. It was named once in a SOP and never wired anywhere, so it was a promise the system did not keep. Removed from the design rather than carried forward as decoration.

## [0.9.64] — 2026-07-26
### Added
- **A 分公司's branch drift comes and finds it** (`stop_branch_drift`). The question: an external branch office lives in a worktree, so it "invocably faces the problem of disagreeing with main/master and having stale files" — what do we do with it. The audit's answer was that the **machinery was already right and nobody was being told**. Every shared-state hook has pierced a worktree to the main checkout since 0.9.52 (`board.main_checkout`), so the branch's stale copy of the card store was inert to the hooks; what no one could see was the branch itself. Live numbers at the time the Boss asked: **77 commits held, 14 behind, and one tracked file uncommitted for four days**.
  - **Three triggers, each independent, each naming its own remedy.** **未合并** = commits held past `thresholds.branch_drain_hours` (24), keyed on the **oldest** held commit, because three commits held for a week beat thirty held for an hour. **落后** = `thresholds.branch_behind_commits` (10) behind, and the nudge says *why* being behind matters: the branch carries a git-**tracked** copy of the card store, mail lane and review markers, so a stale branch is a stale org in every path resolved from it. **未提交** = a tracked edit older than the same drain dial.
  - **未提交 is the one that actually bit.** The dept's own brief carried the growth target they ratified on 07-22, written back into `.claude/agents/Marketing.md` and never committed — while the branch SOP correctly sends the office to read its brief at the **main** checkout. So the office had been reading a brief missing the very number it had written down, for four days, with nothing anywhere in the system able to say so. Untracked files are excluded on purpose: a worktree legitimately carries permanent per-office state (`office.json`, nudge state), and counting `??` would nudge every session forever.
  - **Branch-office-only** (`hooklib.local_office`), because the 分公司 self-merges and is the one who can act; firing this at the CEO would nag the one session that cannot drain without the L2 pass. Advisory, fail-open, one nudge per **trigger set** (hashing the counts would re-fire on every new commit — 0.9.60's lesson), state kept at the worktree so two offices never overwrite each other's memory.
  - **Two bugs the tests caught before the field could.** `git status --porcelain` encodes state in fixed columns, so stripping the output shifted every path by one character: the count was right and the clock silently never resolved. And git octal-escapes non-ASCII paths by default, so on an org whose paths are nearly all CJK the age check could never open the file it was judging (`-c core.quotePath=false`).
- **Branch SOP: sync at 上岗, land level at ship, and never re-type a carry.** New step 3 measures `rev-list --left-right --count` and fast-forwards before any work. Step 8 adds `merge --ff-only` back into the worktree after the self-merge, since `--no-ff` leaves the branch one behind by construction and skipping it is how the gap only ever grows. For a diff that crosses owned paths, the CEO must **cherry-pick the named sha**: a carry re-keyed by hand puts one piece of work on two lineages that share no commit, which is exactly how master shipped superseded article wording for two days while the corrected text sat on the branch. 收工 now says to commit every tracked edit and leave nothing merge-ready unmerged.
- 432 tests (up from 409).

## [0.9.63] — 2026-07-26
### Added
- **One card per seat, each seat named for its card — the Boss's design, now held mechanically.** Per-card release was already doctrine (SKILL §7); what was missing was the naming that makes **sequencing** safe and the bound that stops a seat accumulating.
  - **`pretool_spawn_guard`, two new blocks.** A dispatch handing one seat **2+ cards** is split (boundaries disjoint → parallel seats each in its own worktree; overlapping → sequence, the rest stay queued). A **single-card** dispatch under a bare dept handle must be `<Dept>-<NNN>`.
  - **`stop_capacity`, one new finding.** A seat that has closed **`seat_cards_max` cards (default 3)** and holds none is flagged for retirement. Queue-pull and re-tasking route around the spawn-time rule, so the closed-card count is what catches accumulation however it happened. Flagged only **between** cards: telling a working seat to retire mid-turn is noise, and the retirement is free the moment it holds nothing.
  - **The number, not a slug.** `-<NNN>` is numeric, so `base()` still reduces it to the dept for every roster, brief and stall check, while the handle carries the identifier the board and the nudges already speak. Two numbered seats never collide, so a sequenced next card can spawn **the moment** the current one is told to stop — a shutdown request only lands when a teammate's turn ends (2026-07-15: a released pane kept burning opus while the harness minted `-2`). A slug (`Frontend-adoptcard`) breaks both halves: `base()` strips digits only, so it reads as a dept nobody staffs.
  - **Read off live prompts, not guessed** (the 0.9.51 lesson). Cards are named two ways in real dispatches — `"dispatched by the CEO for card #377 (platform task 81)"` and `"read your two cards IN FULL: docs/board/361-…md and docs/board/363-…md"` — and a bare `#NNN` elsewhere is **context** (a parent, a grounding doc, a frozen window), never the seat's card. Counting every `#NNN` would have stayed silent on every genuine spawn; reading only assignment-shaped mentions catches both live seats.
  - **The prescription is anchored on the DEPT (`subagent_type`), not the handle.** Their CEO already invents task-named seats organically — `spacefix352`, `iofix338`, `ioaudit362`, `fencefix359` all appear as completed-card owners on the live board — and each carries its number with **no separator**, so `base()` cannot strip it: they read as departments nobody staffs, find no agent brief, and never match a card's `dept` in a liveness check. The instinct was already right; only the shape was wrong. `spacefix352` + `subagent_type: Frontend` now prescribes **`Frontend-352`**, not `spacefix352-352`.
  - **Doctrine** in SKILL §7 and `reference/teammates.md`: overlap keeps a seat **warm** (sequencing over the same files is exactly where its context is an asset, so don't pay full onboarding to discard the knowledge most relevant to the next card); a change of ground retires it. **Bloat is a quality failure before it is a cost one** — a seat carrying several cards' abandoned approaches re-proposes them, the same shape as a decision left in prose re-teaching its own dead design. **The Boss reads each pane's context percentage themselves, and their call overrides the counter in both directions.**
- 409 tests (up from 398).

## [0.9.62] — 2026-07-26
### Fixed
- **"On your desk" was counting a note about their queue as a job in it** (found by the Boss asking me to check the mechanism). One register, two surfaces, two answers: the web board read **4** while the Obsidian desk mirror read **3** for the same data. The extra item was an **ambiguity notice** — a card the system generates to describe the queue, not an ask in it. `resolve_by_dept` has excluded notices since 0.9.21 with a comment saying exactly why ("counting them made each notice amplify the next"), and the desk mirror honoured it; the panel's `isInfo` never learned the rule. It now checks `notice`, so both surfaces file a notice as Information.
- **`@BOSS-DONE[<dept>]` had been permanently broken for five days, and it was minting the notices above.** A dept-level DONE resolves only when exactly **one** open ask exists, and the count included **info** items. An info item asks nothing of them: it is never what a DONE resolves, and it leaves the desk only when they toggle it read. Their CEO held **7 open info items, the oldest 5 days old**, so every dept-level DONE saw 7, refused to resolve, and raised a notice — which the panel then counted, producing the next one. Info is now excluded, and a dept with nothing real open resolves nothing without inventing an ambiguity.
- **"In flight" was computed three times and had started disagreeing with itself.** 0.9.61 taught the Tasks-tab filter that a passed card is still in flight (its last step is the CEO's merge) but left the masthead chip and the tab badge on their own copies, so both would have read one low the moment a card cleared L2. One `inFlight(t)` now serves all three, guarded by a source test that fails if a fourth copy appears.
- 398 tests (up from 243 counted — the `skills/orchestrate/scripts/` suite is now included in the tally, which it should have been all along).

### Still open, their call
- Their 7 info items never age out on their own; they leave the desk only when they toggle read. That is by design, but it is what made the DONE fault permanent, so a "fold info older than N days into History" rule would stop the shape recurring.

## [0.9.61] — 2026-07-26
### Added
- **排序 on the Tasks tab** (the Boss's ask, verbatim: "urgent first, then newest first"). That is the default; three alternatives sit beside it: **最新** (newest), **停滞最久** (longest in stage, the stall view), **按阶段** (the old pipeline-band order). Newest is the durable `#NNN` descending, which unlike a timestamp does not move when a card changes stage. Unset priority sorts last rather than pretending to be P0. The group floats right of the filters, wears no border until hovered, and only the chosen one takes the coral ring.

### Fixed
- **已过审 on a card still sitting at 派工 — every L2 chip on the board was a phantom.** Platform task ids restart every session, so a marker written as `49.pass` in one session attaches to whatever card happens to hold task_id 49 in the next one. All four L2-marked cards on a live board were exactly that: #299, #314, #316 and #358 wearing 已过审 from markers **5 to 8 days older** than the stage they were sitting in. It is also why the stall sentinel reported 5 cards 待合并 and their CEO's merge sweep found nothing to merge.
  - **A marker must be no older than the card's stage clock.** `_review_markers` now carries each marker's mtime and `_attach_l2` compares it against `since`. A marker predating the current stage cannot be a verdict on the current leg, whichever id matched. Five minutes of grace absorbs `since` being minute-precision; the collisions this rejects are days out.
  - No stage clock to compare against → a durable `#NNN` is a permanent identity and is trusted; a `task_id` is not, and is refused rather than guessed.
  - **This retires the 0.9.55 ambiguity honestly, so a `.pass` now MOVES the card.** It used to only chip, because a pass on a todo/doing card could have been either a pending merge or a stale marker. A surviving pass is now a verdict on this leg: 审查 is cleared, 完成 is drawn as the step still owed, and the card counts as **In flight** — its last action belongs to the CEO. Leaving it at 派工 while the age chip already read 待合并 made one card contradict itself.
- **The capacity sentinel was firing into an external dept's branch, ordering it to assign the CEO's cards.** My own 0.9.59 regression: replacing the `leadSessionId == session_id` check dropped the lead-only guarantee those lookups were quietly carrying, and the cwd anchor was being handed a root already pierced to the main checkout — so every session under the project matched the CEO's team.
  - `team_key` now matches the session's **own** cwd, **exactly**. A branch office and a dept worktree both live under the project root, so anything looser hands them the CEO's team and task store.
  - Second, independent gate: `hooklib.local_office` reads the nearest `.claude/office.json`, and a 分公司 session never runs the CEO-team pieces (`stop_capacity`, `stop_stale_stage`, `stop_task_reconcile`, `session_start`'s id detacher). The spawn guard is deliberately left ungated — a branch guarding its OWN spawns is correct.
- **`dept_target` replaces the 0.9.60 multi-desk count.** Counting how many live depts the prose mentions was not enough: #268 names two departments but only one of them was live, so it still read as a single ASSIGN target. A dept field now has to **reduce** to one handle — parentheticals stripped, so `Frontend (sonnet seat, diagnosis leg)` is still Frontend while `Backend-Engine (types) + Backend-IO (parse/render) — CEO writes the field-model spec` is a card the CEO must split.
- 243 tests (up from 231).

## [0.9.60] — 2026-07-26
### Fixed
- **The capacity sentinel woke up from 0.9.59 and immediately started nagging about cards that were deliberately held.** It blocked their turn twice with the identical five-card alarm; their CEO's answer both times was that all five were deliberate holds already on record (two awaiting its own scoping, one a post-launch park, one prerequisite-blocked, one parked-with-evidence). Three separate faults, all now fixed:
  - **A recorded hold is not a stall.** Four of the five carried a non-empty `blocked_on` — which is precisely the CEO recording *why* the queue is not moving, i.e. the discipline this sentinel exists to enforce. Re-raising it inverted its own doctrine, and no reply could ever clear it because nothing was wrong. A card with `blocked_on` is now exempt (a `—` placeholder still counts as free).
  - **ASSIGN takes exactly one owner.** The fifth card's dept read `Backend-Engine (types) + Backend-IO (parse/render) — CEO writes the field-model spec`: a card still to be **split**, for which "ASSIGN them or the queue never moves" is an instruction nobody can obey. The check now requires the prose to name **exactly one** live desk, by base handle, so `Frontend` + `Frontend-2` still counts as one target.
  - **"One nudge per state" was not true.** The signature hashed the entire pending id list, so any unrelated card born or completed anywhere on the board re-armed the identical alarm. It now covers the **trigger set only** (idle desks, unassignable cards, registrar state, whether a queue exists at all). Same complaint → same signature → silent.
- **The nudge now names the durable `#NNN`, not just the widget id.** It was reporting "card(s) #36, #30, #50, #12, #65" — five numbers that appear nowhere on the board, because those are session-scoped widget ids. It now reads `#268 (widget 36)`.
- 231 tests (up from 227).

## [0.9.59] — 2026-07-26
### Fixed
- **Six hooks were silently inert because they looked up the team and task stores under the wrong key.** Their report was "the board is just stale": the task widget showed #369 in-progress while the Tasks tab had it filed under `todo`, unlinked. The board was faithful — the **card** was stale, and the piece built to heal exactly that (`stop_task_reconcile`, 0.9.58) had never once spoken.
  - **The platform files `~/.claude/{teams,tasks}/session-<8hex>` under the id the session carried when the store was BORN, and that key does not track the running `session_id`.** Proven on their live project: the hook payload said `49310ed7` (whose task dir is empty) while the entire roster and 79 live widget tasks sat under `e103ac6e`. `~/.claude/teams/session-49310ed7/` does not exist at all.
  - Everything keyed on the current id therefore went quiet **without a single error**: `stop_task_reconcile` (never reconciled — 39 cards sat unlinked), `stop_capacity`, `pretool_spawn_guard` (the collision guard simply stopped guarding), and both `session_start` sentinels.
  - **`stop_stale_stage` was worse than quiet — it was lying.** An unresolvable roster read as "every seat is dead", so it flagged 28 cards as abandoned when 7 of them belonged to a **live** Backend-Engine. Liveness findings are now withheld entirely when the roster cannot be resolved: **`live = None` (unknown) is no longer the same thing as `live = set()` (nobody home)**, and only 待合并 / 未送审, true regardless of who is alive, still speak.
  - **`session_start.detach_stale_ids` was worse still — it was destructive.** It reads a task's absence from the store as proof that its id died, so an unresolved store dir reads as *every* id died and it strips `task_id` off the whole board in one pass. It now refuses to sweep when the store cannot be **found**; an **empty** store still sweeps, because that is a genuinely fresh lead before its first `TaskCreate`. Missing is not empty.
  - **Fix: resolve by PROJECT, not by id.** New `hooklib.team_key` / `team_config` / `tasks_dir`. The current id is tried first (cheap, and correct for a fresh session); when it does not own a store, the lead member's `cwd` inside a team config is the anchor — it survives resume, compaction and re-keying. Newest config wins when a project has led several teams. **No root, no guess:** without a project to anchor on it returns None rather than borrowing another project's team. ~5ms.
  - **Field-proven while it was being written**: the plugin runs from the working tree (the `mycompany` marketplace is a `directory` source), so their next turn end picked the fix up with no cp, no reload, no restart — 39 cards relinked and #369 moved to 执行 against widget task 73 on a live board.
- 227 tests (up from 218), including the resumed-lead resolution path, the refusal to borrow another project's team, and the detacher's refusal to sweep a store it cannot find.

## [0.9.58] — 2026-07-25
### Fixed
- **The board no longer drifts from the task widget** (a field report: the widget showed #342, #357, #359 in-progress while the board read `todo` for two of them and had no widget id at all for the third). **Diagnosed step by step rather than guessed**, and every link in the chain was sound: `find_task` resolves widget id 59→#342 and 61→#357 correctly · the widget store really does hold both at `in_progress` with dept owners · and feeding `posttool_task_sync` the exact real payload flips `todo`→`doing` first try. So the mirror logic was never broken — **the hook simply never ran for those calls.** A dept claims through the **Registrar**, so the `TaskUpdate` happens in the Registrar's session and not the CEO's.
  - **Chasing which session loads which hooks is the wrong fix; the sync must not depend on catching the tool call.** Same shape as the 0.9.46 problem (completions missed `BACKLOG.md` because the tool-keyed hook didn't fire) and the same answer: **`stop_task_reconcile`, a Stop-time reconciler keyed on durable state** that converges no matter who called what. It reads this session's task store (`~/.claude/tasks/session-<8hex>/*.json`, which persists across resume) and heals three drifts, all **forward-only**: ① widget `in_progress` + card `todo` → card advances to `doing`; ② widget `owner` set + card `dept` empty → dept filled; ③ a card with no `task_id` whose durable `#NNN` leads a widget subject → the link is backfilled.
  - **It never downgrades.** A card at `doing` while the widget still says `pending` means the dept flipped its own status and the widget lagged; the dept is the more truthful witness there. `completed` stays owned by `posttool_backlog_log` / `stop_done_sweep` — this piece never retires anything. An ambiguous `#NNN` is refused rather than guessed (that is what birthed ghost cards on 2026-07-20).
  - Runs **before** `stop_stale_stage` in the dispatcher so the stall check judges reconciled truth rather than drifted status. Rides `stop_dispatch`, so no new registration and it runs live.
  - **Dry-run against their real widget store: 64 tasks read, 3 heals — #357 `todo`→`doing`, #359 and #360 linked to widget ids 63 and 64 — and the other 61 left untouched.**

## [0.9.57] — 2026-07-25
### Added
- **`stop_stale_stage` — cards nobody is advancing now come and find their** (their word: "yes build the fix you proposed"). 0.9.55 made the L2 states legible on the board; this makes them arrive at turn end without their going looking. Advisory only: one stderr line, **never blocks**, capped at 8 rows, and it speaks **once per change** in the finding set rather than every turn.
  - **Ownership, not stage, is the signal.** Three kinds: **待合并** (a `.pass` on file — theirs: verify, FF-merge to the reported sha, complete), **未送审** (`review` with no marker — never submitted, so nobody is reviewing it), **派工/执行** (a clock past the threshold with **no live seat** for that dept — queued to a dept that never picked it up, or abandoned mid-work).
  - **Liveness is what makes it honest, and it is why the check cannot key on the card alone.** A card 18h in 派工 whose dept pane is **alive** is a working queue and stays quiet; the same card with a dead pane is an orphan. Liveness = **presence in the team config's `members[]`** (a clean shutdown removes the entry) — never `isActive`, which is a busy-flag that reads false on a demonstrably responsive teammate. Not the lead session → says nothing rather than guess.
  - Threshold is `stale_stage_hours` in orchestrate.json, default **24**. Rides `stop_dispatch`, so **no new registration and it runs live**.
  - **Caught in dry-run before shipping:** `—` is cardlib's EMPTY placeholder, and plain truthiness read it as a department, flagging every unassigned card as a stalled queue (32 findings → 28 once fixed).
  - **First run on the live board: 22 cards queued 27–51h to depts with no live seat, 5 passed and awaiting the CEO's merge, 1 never submitted.**

## [0.9.56] — 2026-07-25
### Fixed
- **The L2 chips render on the card FACE, not only inside the modal** (Boss: "where do that three chips show?"). 0.9.55 wired `l2chip()` into the modal's `.ptags` row only, so `已过审` / `封驳` / `未送审` were invisible until a card was clicked open — which defeats the entire point, since the value is seeing **at a glance** which of the 18 gate cards needs the CEO, which needs the dept, and which nobody owns. The chip now sits beside the dept chip and the status pill on the collapsed face too, in both the grid and the modal.

## [0.9.55] — 2026-07-25
### Added
- **The Tasks pipeline now reads the L2 evidence on disk, so 审查 stops being an honour-system stage** (Boss: "how do we detect task's every stage?" then "what happened to all these cards?"). `审查` was the one stage with **no mechanical detection at all**: the platform widget enum is only `pending`/`in_progress`/`completed` so it cannot express review, no hook ever writes `status: review`, `pretool_review_gate` only *blocks* completion without a `.pass` and never *marks* the card, and **the board never read `docs/reviews/` at all** — so a card parked at the gate drew as 执行. `_review_markers()` + `_attach_l2()` now stamp every card with `l2` = `pass` | `fail` | `''`.
  - **Marker keys, field-verified on a live board:** files land as `208.pass`, `111-leg2-fe.pass`, `1.report-expert-prior.pass.archived`, so the id is the token before the first `.` with any `-suffix` trimmed; `.archived` markers are retired and never count. Doctrine says reviews key on the platform `task_id`, but **ids die per session so the durable `#NNN` is what is actually on disk** — both are matched.
  - **Three states that all rendered as "review" are now distinguishable by chip:** `已过审` (a `.pass` on file — through the gate, waiting on the CEO to verify and merge), `封驳` (a `.fail` — bounced, the dept is reworking), `未送审` (status says review with no marker at all — never actually submitted, so nobody is reviewing it).
  - **A `.fail` moves the stage** (unambiguous gate evidence, outranks the hand-written status). **A `.pass` deliberately does NOT** — on a `todo`/`doing` card it is ambiguous between "awaiting merge with a sloppy status" and "stale marker from an earlier leg", so it gets a chip that asks them to look rather than a stage that asserts.
  - The age chip reads **`2d 待合并`** instead of `2d in 审查` once a card has passed, because a passed card is not in review any more — it is waiting on the CEO.
- **What it found immediately on the live board:** their "In review 10" was under-reporting. **18 cards sit at or past the L2 gate — 11 with a `.pass`, and 8 of those were filed under `todo`**, invisible. Of the 10 they was looking at, **3 had passed L2 two days earlier and were waiting on the CEO to merge**, and **7 carried no marker at all** — they claimed review and were never submitted. Zero `.fail`, so nothing is in a bounce loop.

## [0.9.54] — 2026-07-25
### Changed
- **The echo gate is retired; the echo is now SUMMONED by the Boss** (their call: "how about we just make it simple. make it a slash command that invoked by `/echo` or Echo in text. only then CEO provides the echo table."). `hooks/pretool_echo_gate.py` and its 35 tests are **deleted**, and the `PreToolUse` matcher with them.
  - **New `echo` skill** (`/clock-in:echo`), plus the word **"echo" / 「读回来」 anywhere in their message** — on either trigger a 回声 read-back is **mandatory** before dispatch. The CEO also **offers one proactively** on a marked screenshot or a braided multi-part description, the two shapes that have actually cost them rework.
  - **Why it went:** four field bugs in one day (0.9.49 ×2, 0.9.51, 0.9.53), every one the same mistake — **the hook inferred conversational state by parsing a transcript nobody controls.** A byte-sized window a single screenshot could overflow · assistant text not yet flushed mid-turn, which made the doctrine it printed impossible to satisfy · teammate pings arriving as user-role messages · and finally the Boss's own "do it" read as a new ask, which deferred the spawn they was pushing for, forever. The transcript is an incidental artefact, not an API: its format drifts, its plumbing looks like human speech, it flushes on turn boundaries, and its entry sizes span four orders of magnitude. **Their judgement was the right substrate all along** — they are the one who knows when an ask of theirs was fuzzy.
  - **Everything valuable survives unchanged:** the table format and its three load-bearing columns (`which contract row` — the binding step, where "passed L2 but still wrong" actually comes from; `what it'll look like after` — their instant-recognition-by-eye moved to the front of the pipeline; `if you don't reply` — so "3 wrong" is a sufficient reply), one-row-per-ask, separate-then-bind on prose, post-it-then-END-your-turn, and their reply being the green light. Only the enforcement layer is gone.
  - `@NO-ECHO:` is deleted — with nothing to bypass, an escape hatch is noise.
  - **Honest residual risk, recorded rather than papered over:** opt-in asks them to remember at the moment they are least likely to, since the original complaint was that they *did* trust blindly after handing over marks. That is why the proactive rule is not optional politeness. If the CEO skips it in the field, the cheap net is a Stop-hook **nudge** — which can never livelock or defer a spawn the way a `PreToolUse` block did.
  - The retired hook was also neutered in the live plugin cache on the spot (hook file *contents* run live), so the running session ungated immediately rather than at its next load. 218 tests.

## [0.9.53] — 2026-07-25
### Fixed
- **Echo gate: the Boss's confirmation is the green light, not a new ask** (a field report: "it failed to spawn teammates for several turns"). 0.9.49 made the turn break the mechanism and 0.9.51 stopped teammate pings re-arming it, but **the Boss's own messages still re-armed it** — so the gate demanded a confirmation and then treated that confirmation as a new thing needing confirmation. Infinite regress, visible verbatim in their screenshots: `what you asked: spawn the teammate now` … `if you don't reply: spawning next turn (gate-mandated order)`, then `@NO-ECHO: 「do it」 = your direct confirmation of the read-back table you just approved … the spawn fires on my very next turn (the dispatch gate resets on every message from you)`. **The harder they pushed, the further the spawn receded.**
  - **A read-back is now consumed by the DISPATCH it covers, never by them answering it.** `_dispatched()` detects a real dispatch in the transcript (a `TaskCreate` tool_use, or an `Agent` tool_use carrying a teammate `name`); one-shot spawns — 审查官 · 督察 · staff · experts — deliberately do **not** consume it. So "do it" / "go" / "spawn it now" after a read-back **clears** the gate and the CEO dispatches on that same turn; only their next ask *after* the round has been dispatched owes a fresh read-back. A new image still owes one regardless, mid-round or not.
  - Cost is now **one turn per round**, not one per card and not one per message from them. Doctrine and the block text both say plainly: **never defer a dispatch again after they have pushed for it.**
  - 6 tests including an explicit termination check (four consecutive pushes all dispatch rather than deferring), that a one-shot spawn doesn't burn their read-back, and that a new image re-arms mid-round. Three 0.9.51 tests updated: they had encoded the buggy re-arm-on-every-message behaviour. 253 total.

## [0.9.52] — 2026-07-25
### Changed
- **The mockup's nav bar is now the board's nav bar, and the left rail is gone**. A masthead carries the serif project name with the org's live numbers beside it — **`N on your desk`** (coral when it is not zero), **`N in flight`**, and the freshness stamp — over a row of tabs where **each pane carries its own count**: Tasks, Departments, Decisions, Mail, Archive. The shape of the org is now legible before a single click. Losing the 186px rail gives the content the full 1400px, which is what the card grid wanted: the Tasks pane went from three columns to **four**, Departments from three to five, and a mail subject has roughly 300px more room before it truncates. The rail's collapse toggle and its localStorage key go with it; the theme toggle moves into the masthead.
- **The other six panes join the card language.** Every surface on the board now shares one radius, one border and one background token — the desk columns, the KPI tiles, the SoT band, department cards, the mail and finance tables — instead of the four different radii that had accumulated. **Departments** gain the card hover-lift the Tasks pane uses. **Decisions**, **Archive** and the **branch-office** strip sit in proper panels rather than floating on the page background.
### Fixed
- **A department card no longer prints "default model — no live override this session" ten times.** The model pill already names the model and its tooltip already says the frontmatter default, so only a live spawn override earns a line.
- **The task-widget pill is shown only for a numeric id.** The `task_id` field is sometimes written as prose (the field project has a card reading "never widget-registered; closed by hand with reason — see 状态注"), which is a note, not an id, and would have been rendered as one.

## [0.9.51] — 2026-07-25
### Fixed
- **Echo gate: teammate reports no longer re-arm it** (field report CEO-283, the third and last of the 0.9.47 shakedown). Exactly right: 0.9.49 made the turn break the mechanism, and every seat reporting in silently invalidated the marker before the CEO's next turn could use it. The 59-card batch and #355 sat queued on widget bookkeeping while the cards themselves were correct on disk.
  - `_direct_user_ask` now excludes **user-role plumbing**: teammate reports and `SendMessage` traffic (`Another Claude session sent…` — the common wrapper, and the one the field report's guess missed), `<teammate-message`, `<task-notification`, `[SYSTEM NOTIFICATION`, `{"type":"idle_notification"`, plus wrappers verified in a live transcript that the report didn't name: **`Stop hook feedback:`** (hook stderr is fed back as a user message, so the gate's own block text re-armed it), `<system-reminder`, `<local-command-caveat`, `<local-command-stdout`, `<command-name`, `<command-message`, `Base directory for this skill:`, `This session is being continued from`. Only their real text and images arm the gate now.
  - **Matched as a PREFIX of the stripped text, never containment**, so a message that merely quotes a wrapper is still heard as the Boss. A mixed message counts as theirs if *any* block is genuinely theirs.
  - Empirical note worth keeping: in a live transcript the teammate wrapper appears **2,462 times** against 12 for the `<teammate-message` form the report guessed, so the frequency-dominant string was the one that mattered. 9 tests (four seats pinging, hook feedback, their real message still arming, prefix-not-containment, mixed blocks); 247 total.

## [0.9.50] — 2026-07-25
### Added
- **The Tasks pane is a pipeline board**. Three status columns are replaced by a responsive card grid where **every card wears the org's own pipeline**: **未派 · 派工 · 执行 · 审查 · 完成**, green behind, coral where the card is now, dim ahead. This is the one idea in edict's dashboard that a column cannot express: a status tells you a card's state, a pipeline tells you *where it is in the flow the org actually runs* — and because 审查 is the L2 gate, a card parked at the gate for four days is now the loudest thing on the page (the field project had exactly that: #217, four days at 审查). 未派 is the Boss's own existing word for a card with no department, so an unassigned card and a dispatched-but-not-started one stop looking alike. Filters across the top (In flight · Doing · In review · Todo · Blocked · Done · Everything), sorted by what is moving first, priority holding inside each band. **A click opens the fielded card as a modal** rather than expanding it in place, which at 30+ cards used to push the page down and lose their scroll position; `?task=<id>` deep-links one card, the same trick as `?tab=`, and is what makes the modal screenshot-verifiable.
- **The two id kinds are now told apart on sight, using the colour rule the board already had.** **Coral `#NNN` = the durable project card** that outlives every session; **neutral `#N` = the task-widget id**. A card with no neutral pill was never registered with the task tools, which is exactly the question the Boss asked ("so I can tell which tasks are registered by task tools"), and the tooltip says so in words.
- **`since` — the card's stage clock** (the file clock was the wrong signal). The age chip used to come from the card FILE's mtime, which any touch resets: a hygiene sweep, a digest regen, a field edit. It answered "when was this file last written", never "how long has this been sitting". `cardlib` now stamps `since` **when a card enters a status**, from three sources in descending accuracy: the write path (`set_fields`/`retire`/`new_card`, exact), a turn-end sweep against a tiny id→status map (`stamp_since`, which catches an Obsidian property edit, a dept editing its own card, a 分公司 session), and a backfill from the file clock for cards that predate the field, so a legacy card is not born reading `0m`. The chip reads **"22h in 审查"**: approximate on old cards, exact the first time each one actually moves.
### Changed
- **Dark-first, with a light toggle** (their call, given edict's dark dashboard). The board is a monitor that sits open all day, so it defaults dark and they flip it by hand instead of following whatever the OS decided; the choice persists in localStorage and `?theme=` still pins a screenshot. The dark palette is deepened to the tone they picked (page `#16150f`, surfaces `#232120`), keeping Claude coral as the accent rather than edict's blue and purple. **Nothing wears red**: red is auspicious in the almanac tradition the palette borrows from, so a stalled card and a blocked card are amber. **No emoji** anywhere, where edict's own pipeline nodes and tabs are emoji throughout.
- **The shell widened to 1400px** so the grid gets its third column, and a dept cell carrying prose ("Backend-Engine (grounding: which engine emissions the web face must mirror) → Frontend (web fix)") wears only its handle on a card face, with every word kept in the tooltip and shown in full in the modal. On a card face that blob outweighed the title.

## [0.9.49] — 2026-07-25
### Fixed
- **HOTFIX — the echo gate blocked dispatch even after the CEO complied** (field report CEO-279, hours after 0.9.47 shipped: "blocks TaskCreate even after I post the @NO-ECHO declaration it asks for (twice) … its transcript scan finds ZERO assistant-text entries in the tail (grep finds my marker 5x, scanner sees decl=-1)". Effect: **no task cards could be registered that session.** Its diagnosis was right, and both root causes were mine.
  - **The scan window was measured in BYTES, which is the wrong unit.** A single base64 image or a large tool result routinely exceeds 240 KB *on its own*, so the 256 KB window could hold as few as **one entry** and silently evicted the very echo it was scanning for. Measured on a real 3.3 MB transcript: the old window held **16 lines, 3 assistant entries, 1 carrying text**. Cruellest form of it: on an image round an attached image is the line that pushes everything else out. `_tail_lines` now reads backwards until **`MAX_ENTRIES` (300) complete entries** are in hand (8 MB runaway guard), so a stable number of *turns* stays in view whatever their size. Same transcript now shows **97 assistant entries** instead of 3, in 7 ms.
  - **An assistant message only reaches the transcript when its turn ENDS**, so text written earlier in the *current* turn is invisible to a PreToolUse hook — and 0.9.47's block message told the CEO to "post the table FIRST, in this turn, then dispatch", which is impossible to satisfy. That is why it looped. Doctrine corrected everywhere: **post the echo (or `@NO-ECHO:`), end the turn, dispatch on the next one.** This is not a workaround for the flush behaviour — it is the point. **A table posted and dispatched in one breath never gave the Boss the chance to say "3 wrong"**; the turn break IS the mechanism, and without it the echo is a monologue. Cost stays one turn per ask, never one per card, since a clearance covers every dispatch until they speak again.
  - 4 regression tests pin both causes (declaration and echo each surviving three 300 KB intervening entries · an image ask not evicting its own echo · an echo 80 turns back still in view). 238 tests total.

## [0.9.48] — 2026-07-25
### Fixed
- **The Archive tab was showing 5% of the history, and nothing newer than 2026-07-09.** `load_archive` read only BACKLOG.md's hand-written `> **✅ DONE — …**` blocks — the pre-table era, which stopped being written when `log.py`'s append-only `| date | id | dept | task | status | sha | note |` table took over. On the field project that is **24 entries on the panel against 442 on file**, and it means 0.9.46's whole point (completions reaching BACKLOG with or without the task widget) landed in a file the board never opened: the sweep ran all morning and the Archive still ended sixteen days ago. Both eras are now read and merged newest-first, a machine row winning a `#NNN` collision because it carries the sha and the L2 note; a row is rendered with its **date · dept · sha · note**, so "swept from card status · no L2 pass on file" is visible where it matters rather than only in the file. A dept cell carrying prose ("Backend-Engine (sonnet seat, diagnosis-first)") wears the handle on its chip and keeps every word in the tooltip.
- **The mail lane hid its own time column.** Every `.ftable` cell is `white-space: nowrap`, so the subject — the longest cell — set the table's width, the lane overflowed its box, and `time:` (0.9.33, backfilled in 0.9.43) sat off-screen behind a horizontal scroll nobody scrolls. The subject is now the single elastic cell and ellipses at the box edge (full text in the tooltip), so the column that two versions were spent on is finally on screen. `time:` is sender-written and the field writes prose into it (`2026-07-24 (crossed-message correction, minutes after your carry-queued note)`), so the column shows the machine head (date · clock) and keeps the sender's words in the tooltip.
- **The canon index truncated the half that identifies it.** `.ctopic` shrank before the prose pointer did, so the keys read `citely-cn…`, `pp-d…`, `eresour…` — the topic key is what the canon is *scanned by*. The row is now a grid: the key holds its own column and wraps, only the pointer gives up width.
- **`#—` on the ship tail.** `stop_done_sweep` always wrote the 6-field `date · #<card> · #<session id> · …` line, filling an absent session id with a dash — and the sweep IS the widget-less path, so nearly every swept row printed a literal `#—`. It now takes the 5-field shape when there is no session id (what the widget path already does), and the panel collapses ` · #—` runs on the lines already written.
### Changed
- **Every list badge counts the file, not the page.** The panel is slices of long files, and each count was the slice's length: **Recent rulings said 14 when DECISIONS.md holds 252**, the mail lane said 30 against 75 letters on disk (and a branch office's letter count was capped at the same 30), the Archive said 25. Counts now come from the whole file and each list says what it is showing (`showing the latest 14 · the log is docs/DECISIONS.md`), including the desk's History, whose `364` badge sat over a list of 8.
- **The Dashboard's lower half now says WHICH, not just how many**. A **Today** band under the desk names what the four tiles count: **Blocked** (with each card's blocked-on line), **In review**, and **Shipped today**. It reads the cards already loaded — no new source, no new poll — and a column with nothing in it is not drawn, so a quiet org still gets a quiet page.
- **`?tab=<id>` opens the board on one view.** The rail's tabs were click-only and remembered in localStorage, so a tab could not be linked, bookmarked, or screenshot-verified — the panel's own release ritual (headless Chrome before shipping) could only ever see the Dashboard. A URL tab is treated as a visit, not a preference: it never overwrites the tab they left the board on.

## [0.9.47] — 2026-07-25
### Added
- **The ECHO GATE — Boss↔CEO asks are now mechanically read back before dispatch**. Root cause named: this is a **binding failure, not a quality failure.** The contract matrix defines what correct behaviour IS and the Auditor's STEP 0 rigorously checks the diff against the rows a card cites — but **only the Boss can say WHICH row an ask is about.** Bind it wrong and every downstream stage is honestly correct against the wrong target, L2 passes, and it is still wrong on their eyeball; no amount of added downstream rigour catches it, because the rigour is aimed at the wrong row. The **translate mechanism they believed they had did not exist**: the word "translate" appeared in one README sentence and one brain-regime job list, never as a format, artefact or gate — so their "I don't know, it's still not enforced quite well, I'm not sure though" was exactly right, there was nothing to be sure about. `hooks/pretool_echo_gate.py` (PreToolUse on `TaskCreate|Agent`) now **blocks** dispatch while a Boss ask sits in the transcript with no 回声 posted after it. The table gained the two columns that do the work: **`which contract row`** (the binding step) and **`what it'll look like after`** (a predicted after-state, which moves their strongest skill — instant recognition by eye — from the END of the pipeline to the front, since today they only gets to use it after dispatch, execution, L2 and merge). `if you don't reply` states the CEO's default so **"3 wrong" is a sufficient reply** — they are asked to *recognise*, never to *compose*. Two gate strengths, because detection reliability differs: a **marked image has no bypass**; a **description-only ask** clears on an echo or on an explicit, auditable `@NO-ECHO: <why>` line (no hook can tell "run the tests" from a braided three-part request, and a gate with no escape hatch gets routed around). A prose ask is treated as **harder** than a mark, not easier — a mark bounds ambiguity to a region, a description carries no anchor, and several asks braided into one sentence are the highest-risk input the org takes, so on a description the CEO must SEPARATE the asks before binding each. Cost is one line per user turn, never per card (twelve cards after one echo still need one echo); an unechoed image outranks a later text ask; one-shot subagents, tool-result images, and inactive projects pass untouched; fail-open throughout. 19 tests.
- **`reference/dispatch-artefacts.md` — the four dispatch artefacts promoted out of brain regime into the default spine** (echo · 诊断 candidate-cause table · 规格 spec · ①②③ escalation ladder). They were invented as a Fable **context-diet** workaround but are actually **gradient** instruments — what they do is bound how much judgment a cheap head is left holding — so they now apply under every regime. Promoted with the quality gaps fixed rather than lifted as-is: the **诊断 table** gains a probe-cost column, walks by likelihood ÷ probe cost instead of strictly top-down, and makes **"a cause not in the table" a first-class dept finding at any time** rather than an exhaustion fallback (the closed-world fix: the CEO's differential was the ceiling on org throughput). The **规格 spec** was one line (`what · done-when · harness`) carrying the most load-bearing job in the design, and is now authored as five fields — **`What` · `Not this` · `Fixed vs free` · `Done when` · `Evidence`** — where `Not this` and `Fixed vs free` are precisely what make a cheap head safe. The **ladder** is re-anchored on **evidence quality** rather than CEO context cost (that reading is now marked Fable-only) and every rung carries a named **descent trigger**, so ① can no longer loop. §0 records the governing asymmetry: **the Boss's rounds are the scarce resource, not tokens** — one round of re-explaining a missed target costs more than a hundred CEO thinking turns, so spend tokens freely to avoid one. §5 records the honest gap: **no per-agent token accounting exists anywhere in the plugin**, so the two-stage split is believed, not measured.
- **`fable` partially unlocked — two named triggers the CEO executes without waiting for the Boss** (previously a hand-switch only). **Recurrence 复盘**: ≥2 consecutive L2 封驳 on one task where the second reproduces the class of the first → the 督察 runs one-shot on fable. **Ceiling bounce**: a task already escalated to `opus` bounces again on *competence* → fresh producer spawn at fable, never a resume. Both require evidence of a failure that already happened, never "this looks hard". One attempt per trigger ever; a fable bounce ends the ladder; unavailable → report and fall back to opus, never silently substitute; every fable spawn named in the report. Under brain regime both still need the Boss's word (the CEO draws on the same weekly cap).
- **`effort` documented as the second routing dial** (verified against CLI 2.1.219). It changes thinking depth and spend **without** changing tier, and it reaches the two halves of the org by different routes: **one-shot subagents** (审查官 · 督察 · experts · staff) take `effort:` in their agent-file frontmatter; **部门 heads are teammates and cannot be pinned** — a teammate's frontmatter `effort:` is ignored (it honours only `tools` and `model`) and teammates **inherit the lead's** level, so the CEO's `/effort` is a **live org-wide throttle** on the whole department fleet, changeable mid-session with no respawn. Defaults to `high` on Opus 5 and Sonnet 5 in both the API and Claude Code.
### Changed
- **Model menu refreshed to the Opus 5 generation** (the table had rotted to 2026-07-04, still naming `opus` as Opus 4.8). `opus` → **Opus 5** ($5/$25), `sonnet` → Sonnet 5 ($3/$15, intro $2/$10), `haiku` → Haiku 4.5, `fable` → Fable 5 ($10/$50). Added latency, knowledge-cutoff and ctx/max-out columns, which surface a capability argument independent of price: **`opus` knows to May 2026 while `fable` stops at Jan 2026**, four months of library and API drift, and `fable`'s latency is *slower* where `opus` is moderate. Recorded that `sonnet`/`opus`/`fable` share the denser tokenizer so their sticker prices compare directly (fable = exactly 2× opus; opus = 2.5× sonnet at intro), and that **any cost baseline measured on the 4.6 generation under-counts by ~30%** — re-measure, don't scale. Two rot dates flagged: Sonnet's intro price ends **2026-08-31** (the default gets 50% dearer with no code change), and **Opus 5 draws a separate rate-limit bucket** from the Opus 4.x pool.
- **法务部 (Legal) pinned `fable`** as a standing rule in both the SSOT and `/recruit` (Boss's pin): it owns the 红线, its call volume is low enough that the weekly cap never binds, and it is the one domain where a wrong call is a liability rather than a rework.
- **Expert tier splits by prefix — `Prof_` → opus, `Spec_` → sonnet.** A `Prof_` is invoked for authoritative knowledge (what the literature says), which is what the top tier buys; a `Spec_` is invoked for craft outside the calling dept's field, sonnet's strongest suit, reviewed by the caller and gated by L2 anyway. A bounced `Spec_` answer re-runs on opus. Pinned by the 督察 at authoring (`Inspector.md` Job 3).
- **Why the head is sonnet is now recorded as field history, and the reason is the gradient, not the bill** (Boss's account). **Config 1 (opus CEO + opus heads)**: no gradient, so decisions drifted down to the head and the CEO **orchestrated instead of judging** — with a peer on the other end there is nothing to audit, so the CEO degraded into a router; separately, heads were cautious, distrusted sonnet staff, and hoarded the typing at the top tier, so spend went **up**. **Config 2 (fable CEO + sonnet heads)**: heads went cheap, and **a sonnet dept given too much freedom breaks things** — which is what brain regime was built to fix. The rule that falls out: **a head's tier and a head's freedom move in opposite directions, and there is no configuration where the head is both cheap and free.** Of the two objections to an opus head, the **hoarding** one has expired (a model-generation trait: Opus 4.8 measurably under-reached for subagents, Opus 5 reaches for them freely and the guidance is to *cap* it) while the **gradient** one has not, and it is price-independent and the stronger.
- **`reference/brain-regime.md` shrunk 50 → 31 lines**, holding only what is genuinely Fable: the context diet, the Boss's eyes for cosmetic acceptance, the shared weekly cap tightening the fable triggers, and batch-L1. Its stale claim that parity "rests on craft parity: opus CEO, opus heads" is replaced — that parity has not existed in any live configuration since heads went sonnet.
- **The spec fence is enforced end to end, so it is no longer decoration.** `department-sop.md` tells depts that **`Fixed vs free` is binding, not advisory** (disagree → report, don't redesign) and grants them the outside-the-table reporting path; `Auditor.md` folds both into the L2 bars — `Evidence` absent or in the wrong form fails **达标**, anything the `Not this` fence excludes or a FIXED item renegotiated in the diff fails **守界** even when the code is good, and a dept reporting a cause outside the 诊断 table is **correct behaviour, never a bounce**.
- **The Registrar's `haiku` recorded as an AVAILABILITY pin, not a cheapness pin** (Boss's rationale): haiku is the tier that still has its tools when the others don't, so the task desk — the org's single write-path for the task lifecycle — is the one seat that must never lose them. Explicitly exempted from the tiering test, which would otherwise have "upgraded" it.
### Fixed
- **Stale hook text.** `pretool_spawn_guard`'s docstring still claimed "the roster's opus pin is parity-only" (heads have been sonnet since 2026-07-19), and `session_start`'s Fable regime arm pointed only at `brain-regime.md`, which no longer carries the artefact formats — it now names `dispatch-artefacts.md` too.

## [0.9.46] — 2026-07-25
### Added
- **Completions reach BACKLOG with or without the task widget**. `posttool_backlog_log` fires only on a platform `TaskUpdate → completed`, so in widget-gated sessions whole runs of finished work were never recorded: field state on the field project — 24 properly-retired cards, all 24 with a BACKLOG row, versus **91 cards left at `status: done` on the Active board, only 2 of which had a row**. 89 finished tasks had fallen out of the written history. The new `stop_done_sweep` Stop piece keys on the **card's own `status: done`** instead of the tool, and records + retires it through the same shared writers the widget path uses (`log.py` row · Recently-shipped block · `cardlib.retire` into `board/done/`), so both paths converge on identical records and whichever fires first wins. Idempotent (a `#NNN` already carrying a row is skipped), capped at 25 cards/turn, lead-session only, retires by MOVING files (never deletes), and dates each row from the card's own file so an old backlog lands under the days it actually finished. `note` states whether an L2 `.pass` was on file rather than silently dressing an unreviewed card as reviewed. **Opt-in per project** (`"done_sweep": true` in orchestrate.json) — this retires cards and appends to the durable log, so a project adopts it deliberately, never as a surprise on the turn the plugin updates.
### Changed
- **Board replies are typed into the Boss's terminal input, not queued.** 0.9.45 routed answers through an outbox drained by a `UserPromptSubmit` hook, with iTerm2 typing a contentless `Deliver my Boss Board answers.` nudge. In the field that was worse than useless: the nudge submitted with no content, so the session went **searching the board files** for what they meant, and the hook's delivery surfaced as a red "Stop hook error" (exit-2 is how that mechanism talks). Send now types the composed answers **straight into their input** for them to press Enter, so the model receives the actual content. The outbox, the `UserPromptSubmit` hook and the whole queue are deleted; the page falls back to the clipboard when typing cannot land.
- **The pane target is captured at TURN END, not session start** (`stop_iterm_capture`). A freshly-spawned teammate's transcript isn't stamped yet, so the start-time lead check mis-read it as the lead and let it overwrite the Boss's target with its own pane — field case: the captured pane was `✳ Legal (claude)`, so every reply was typed into the **Legal teammate's** input, invisible to them. At turn end the transcript is stamped, so lead-vs-teammate is reliable and the target re-pins to the CEO pane every turn.
- **Read-toggle behaves as specified** (Boss): ticking `read` on an Information row now **folds the card into History immediately** and stages a brief batched acknowledgement, so Send delivers `Read: CEO-221, Frontend-8` — one line, no action wanted. A read marks the item acknowledged, never resolved.
- **The Done column's fold covers CARDS, not just shipped lines** (Boss's long-standing rule, restored in full): 5 or fewer → show everything; more than 5 → show only what finished **today** and collapse the rest into an expandable **Earlier**. Done cards carry no date in the digest, so `load_taskboard` takes it from the card file; undateable leftovers fold to Earlier rather than posing as today's work. On the field project this turned a Done column of ~96 items into 8 visible with 88 folded.

## [0.9.45] — 2026-07-22
### Added
- **The Boss Board is now a two-way desk, and the panel a real dashboard**. The panel stops being read-only display.
  - **Reply / Ask / Read from the browser.** Each open ask carries a **Reply** (a decision) and **Ask** (a follow-up); Information rows carry a **read** tick. Replies/asks stage in a basket (nothing auto-sends); one **Send** flushes them as a SINGLE message. Answering **resolves the item on the board itself, server-side, at Send** — so "forgot to run `@BOSS-DONE`" is impossible by construction. Every write is a CSRF-guarded `POST` (the `X-Board` header contract already used by `/open`) on the 127.0.0.1 daemon; the reply text reaches `osascript` via argv only (no shell/AppleScript injection).
  - **Delivery.** Content always travels via a durable outbox + a `UserPromptSubmit` inbox hook (the one deliverer, marks itself delivered), so a reply is never resolved-but-not-delivered. iTerm2 primes the Boss's pinned pane (id captured at session start) with a nudge; they press **Enter** to hand the batch over. macOS silently drops a synthetic Return from a background process, so true auto-Enter is impossible — tmux `send-keys` would be the only hands-off path.
  - **Dashboard tabs** (edict-adapted, trimmed to our org) on a collapsible left rail: **Dashboard** (a monitor glance — needs-you · in-progress · blocked · shipped-today with health dots — over the SoT compass and the desk), **Tasks** (the fielded kanban), **Departments** (花名册: each dept + the **effective model** it runs on + the 分公司 lane), **Decisions** (recent `DECISIONS.md` rulings + the `CANON.md` settled-answer index), **Mail & Branches** (the 分公司 mail lane), **Archive** (`BACKLOG.md` history + shipped), and **Finance** (an Obsidian Base ledger read straight off disk). Mail/Finance tabs auto-hide on projects without them.
- **Effective per-dept model tracking.** The frontmatter `model:` is only the DEFAULT; the CEO overrides it at spawn. A new `PostToolUse(Agent)` hook records each spawn's `tool_input.model` into the board store, and the Departments view shows the effective model ("running X · default Y"), frontmatter as fallback.
- **Finance view = an Obsidian Base**, not a DB connection. `orchestrate.json` `finance` names a `.base` file; its table view gives the columns and its ledger-folder notes' frontmatter give the rows (markdown-native, no credentials).
### Changed
- **Direction band retired → SoT compass.** The manual `orchestrate-board direction` banner went unmaintained and became noise; the Dashboard's compass is now the SoT's `## Now` (State · Blocked-on-their · Money), CEO-curated and re-read every session, so it can't go stale.

## [0.9.44] — 2026-07-21
### Fixed
- **Branch brief reads at the MAIN checkout**. The branch skill declared shared state (cards · mail · reviews · BACKLOG) lives at `<main>`, but step 1 read the dept brief from the branch's own checkout — an uncommitted brief edit on main was invisible to the 分公司 until commit + merge, forcing a hand-copy into the worktree (the Marketing 经济头脑 mandate exposed it). Org identity is shared state: the brief is now read at `<main>/.claude/agents/<handle>.md`, so a Boss/CEO brief edit on main is live for the branch at its next 上班 with no merge round-trip. `office.json` rightly stays worktree-local (it marks WHICH office a checkout is, not what the office believes).

## [0.9.43] — 2026-07-21
### Fixed
- **Mail `time:` backfill sweep** (field report: the Mail view's time column patchy — empty on most of the day's letters). `time:` is sender-written (0.9.33), and doctrine drifted within a day: live sessions post letters without it, and the CEO also names files without the HHMM stamp. `stop_mail.backfill_time` now fills a missing/empty `time:` mechanically at every turn end: filename stamp `YYYYMMDD-HHMM` first, else filename date + the file clock's HH:MM, else the file clock alone. A sender-written value is never overwritten; dead letters (no fence) stay the postmaster-nudge lane; idempotent, traced under `mail-hygiene`. the live project's patchy letters healed in-flight (the live session ran the sweep from the working tree before release).

## [0.9.42] — 2026-07-21
### Changed
- **Collapsed kanban cards are title-only** (Boss's call): pills + name + dept chip, no prose clamp — the board scans as a list of titles (the name's own "SLUG — description" carries the gist); the fielded card (WHAT / DONE WHEN / BLOCKED ON / ARTIFACTS) waits behind the click or `#x`. Status badges stay on the face.

## [0.9.41] — 2026-07-21
### Added
- **Fielded kanban cards** (Boss chose structure over costume after the 三省六部 comparison; Anthropic theme kept). The edict lesson applied: a card is a form, not an essay. Expanded cards now render **labelled compartments** — WHAT · DONE WHEN · BLOCKED ON · ARTIFACTS, each through the 0.9.40 formatter (done-when's `·` glue becomes checklist rows), tiny uppercase labels over hairlines; `parse_taskboard` now carries `done-when` + `artifacts` to the panel. **Coloured dept chips** (edict's per-ministry coding, Anthropic-muted): deterministic hue per handle via `--dh` CSS variable, light+dark derived pairs; an empty dept renders a quiet grey **未派** chip — a department name opening the `what` prose can no longer masquerade as the dept badge (their #184 confusion). Collapsed faces stay compact (chip + clamped what). Light + dark screenshot-verified.

## [0.9.40] — 2026-07-21
### Added
- **The essay formatter — structured, ADHD-friendly cards**. Root cause of "still": CEO asks carry no literal newlines — they're single-line essays glued with `·`, sentences, and ①-⑳ — so 0.9.37's newline support had nothing to break on. New `fmt()` rebuilds the structure the prose hides, purely mechanically: **sentences end lines** (`。？！；` always, closing brackets stay attached; `. ! ?` only before a fresh capital/`「`/digit so paths and decimals hold), **①-⑳ clauses** become hanging-indent list rows, **` · ` runs** become dotted list rows with a coral marker. Applied to expanded ask bodies, quoted originals, and expanded kanban cards (the collapsed dept·what clamp swaps for a dept line + the structured essay); collapsed faces stay compact clamped flow. Light + dark verified by headless screenshot.
- **`#x` expand-all mode**: open the board at `/#x` and every card renders pre-expanded — one reading pass over the whole desk without a click per card; hand-collapsing a card sticks.

## [0.9.39] — 2026-07-21
### Fixed
Four Boss reports on the 0.9.38 desk, one pass:
- **CLI `--dept` default flipped to `CEO`**, and an explicit `Boss`/`老板` normalises to CEO — "Boss is not dept": they are the audience of every ask, never its raiser; the old default stamped their name into the dept column of every CLI-raised ask (existing `Boss-NN` entries keep their ids — renaming would dangle `@BOSS-DONE` references).
- **Desk `files` cells now clickable**: a plain scalar string rendered dead text in Bases — `files:` is now a YAML list of quoted wiki-links (`- "[[docs/…]]"`), which Obsidian renders as links in both the properties panel and the Bases cell; always a list (empty `[]`) so the property type never flips.
- **Panel ask meta line is a footer in BOTH states**: expanded, `Boss-32 · Boss · discuss` used to wedge between title and body and read as a divider — `.rx` (body/files) now precedes `.rm`, so the meta sits quietly at the bottom expanded exactly as it does collapsed.
- **Path extraction: bare filenames can no longer start with a hyphen** (panel PATH_RE + the mirror's python twin) — killed the `-2026-07-21.jpg` fragment links a date-suffixed name split produced.

## [0.9.38] — 2026-07-21
### Added
- **Obsidian desk mirror** (Boss's ask: the panel's Needs you / Parked / Information sections in Obsidian, with file paths in their own cell). `board.desk_mirror(root)` writes the ask register as generated notes — `docs/board/desk/<id>.md`, flat frontmatter (`section` · `kind` · `dept` · `task` · `ask` · `files` · `updated`), body carrying the full text with clickable markdown links; `files:` extracts project-relative paths via the panel's own PATH_RE (python twin), giving Bases a separate readable column. Sections are number-prefixed (`1 Needs you` · `2 Parked` · `3 Information` · `4 Answered`) so lexical groupBy matches the panel's order; Answered keeps the newest 8. Machine-owned: notes rewrite only when bytes change (Obsidian stays quiet), prune only files stamped `mirror: boss-board` — the hand-written notes in the folder survive. Status truth stays in the JSON store (resolve via @BOSS-DONE / CLI / the CEO). Refreshed at every turn end (stop_boss_board, after captures/dones) and session start; `templates/Board.base` + the field project's live base gain the **Desk** view (grouped by section, sorted updated DESC).
### Fixed
- **Done tail noise** (field report: `2026-07-21 · #38 · — · — · sha` rows in loud coral). Root cause: card-less completions — the CEO's platform bookkeeping chores (review-window closes, marker banking) — wrote dash-filled lines into the Boss-facing *Recently shipped* tail, and the renderer's lone-id fallback dressed the session task_id in the coral durable pill. Now: **no card, no tail line** (the tail is the ship glance; the BACKLOG row + marker-miss trace keep the ledger), a lone leading id pills **neutral** (coral stays reserved for the durable #NNN), and placeholder runs (`· — · —`) collapse before render on legacy lines. the live project's five bare lines removed by hand.

## [0.9.37] — 2026-07-20
### Fixed
- **Line breaks in Needs-you ask text**. It didn't, except in the Direction band (`pre-line` CSS) and before ①…⑳ enumerators: a literal newline in an ask's detail (CLI `--text`, a multi-line marker detail) collapsed into a space and rendered as a wall. `brk()` gains an `nl` mode that also honours literal newlines — applied to the **expanded body** and the **quoted original** only; collapsed titles keep flowing (a multi-line title would wreck the compact row face), the Direction band keeps its CSS path. Verified via headless-Chrome DOM dump on a seeded fixture (newlines + enum breaks both render; default collapsed view byte-identical); the field project's live daemon hot-swapped.

## [0.9.36] — 2026-07-20
### Fixed
- **Double-registered ask slips the collision net** (field case, the field project Boss-13/CEO-166: the trailer nudge fired on an unmarked trailing ask; the CEO registered it via `orchestrate-board add` — `--dept` defaulted to `Boss`, kind `discuss` — AND then re-ended with the `@BOSS[CEO#197]` marker anyway → the same ask twice in Needs-you, and the 0.9.21 collision key required same dept + same kind, which a two-path registration never has). Fixes:
  - **Collision identity = the task key alone.** `add_entry` flags any open non-info ask sharing the `ask_key` (explicit task, else the title's first `#NNN`), regardless of raiser handle or kind. Unchanged guards: info (either side) · notices · same-batch · keyless never flag; nothing auto-resolves — the once-per-set Stop nudge still puts the raiser in the loop (`@BOSS-DONE` the old, or end unchanged to keep both), now naming the registered-twice case explicitly.
  - **Trailer nudge teaches ONE register path**: after an `orchestrate-board add` this turn, end again WITHOUT a marker — the marker would register it twice.
  - CLI `COLLIDES` line and the collision nudge drop the stale "(same dept+kind)" wording. The CLI's `--dept` default stays `Boss` (the Boss's own quick adds carry no handle); a CEO add should pass `--dept CEO`, and the widened key makes the mislabel harmless to detection either way.

## [0.9.35] — 2026-07-20
### Added
- **Boss-signed content review scope**. The L2 round on a Boss-signed artefact still runs — a verdict certifies a tree and their sign-off changed it, and the self-merge guard keys on the `.pass` — but it is now scoped doctrine in three places (Auditor · branch skill §6 · dept SOP): the producer cites the signature in the invocation (where the signed text lives); the Auditor reviews **transcription** (file on disk = signed text — hand-derived numbers are where slips live) + **守界** + **可追溯**, full five bars only for what they did NOT sign; the signed content itself is canon — a `.fail` against it is a doctrine violation; a material error spotted in signed content goes in the report for the CEO to raise with them, never a bounce.

## [0.9.34] — 2026-07-20
### Fixed
- **Board hygiene sweeps** (field case, the field project 2026-07-20 — the Bases Active view broken twice in one day). Two mechanical failures, one cascade: **(a) essay statuses** — sessions write ship-speak/start-speak prose into `status:` ("MERGED 07-20 — L2 PASS …", "COMPLETE — …", "active — …", "parked — …"); Bases groups every unique essay as its own status and `parse_taskboard` finds no canonical keyword so the card misfiles under Todo. **(b) duplicate durable ids** — a hand-written card numbered from conversational memory (or two sessions minting in the same window) claims a `#NNN` another card already wears; `new_card`'s O_EXCL only guards the exact filename, not the number. A duplicated number then poisons the task-sync fill tier: the subject-`#NNN` match turns ambiguous, falls through, and **births a ghost duplicate card** (the field project: dup #189 → ghost #190 wearing the platform task the real card never got; the same cascade earlier left #187/#188 twins and an orphaned hand card collecting essay status because completion could never retire it). Fixes, all fail-open and idempotent:
  - `cardlib.canonical_status()` — first canonical keyword (todo/doing/review/blocked/done) wins, else a synonym map by order of appearance (merged/complete/shipped/pass/landed/closed→done · active/wip/started/in-progress→doing · parked/pending/queued→todo · waiting→blocked), else `todo`; empty/placeholder left alone (unset is a state, not drift).
  - `cardlib.canonicalise()` — active-card sweep: status collapses to canon, junk `priority` values (not P0/P1/P2) to `—`, the original prose preserved as a dated `> 状态注` body line (the 迁移注 pattern). Bases groups become the five states again; nothing is lost.
  - `cardlib.dedupe_ids()` — global active+done+archive scan; a duplicated number's keeper is the done/archive holder first (its number is frozen in BACKLOG history — and retirement rewrote the file, so mtime lies), then the eldest file; every other holder renumbers to the next free id with a dated `> 编号注` body note.
  - **task-sync refuses ambiguity**: a CREATE whose subject-`#NNN` matches multiple unregistered cards fills nothing and births nothing — a marker-misses trace instead of a ghost; the turn-end sweep renumbers.
  - Wired at **every turn end** (`stop_board_digest`, before the staleness regen — sweep writes then reach the digest in the same pass) and **session start** (lead audience, after `ensure_store`); traces land in `.claude/marker-misses.log` under `board-hygiene`.
  - `new_card` files now minted `0o644` (were umask-exec via raw `os.open`).
### Added
- **`time:` field on mail notes** (Boss's ask). Frontmatter `time: "YYYY-MM-DD HH:MM"` — human-readable and lexically sortable, written by the sender (the filename stamp remains the uniqueness key). Wired through the branch skill's mail format, the orchestrate files table, setup doc, the mail nudge's reply-format line, and the Board.base Mail view (new column; template sorts by time DESC, a project's own sort tweaks are left alone). a live project's 22 existing letters backfilled from their filename stamps. Not part of the dead-letter contract — `to:`/`status:` stay the address; `time` is display/sort metadata.

## [0.9.32] — 2026-07-20
### Fixed
- **Dead-letter sentinel** (field case, the field project 2026-07-20, day one of the mail lane): the CEO commissioned a dept report as a file-drop and it landed in `docs/board/mail/` as plain markdown — no `to:`/`status:` frontmatter, so Bases showed empty columns and the unread nudge (correctly) ignored it: a letter no addressee could ever see. `stop_mail` now sweeps the mailbox for frontmatter-less/unaddressed `.md` files and nags the **CEO office as postmaster** (one nudge per state; branches see only their own mail): add the frontmatter or move the file out. Doctrine hardened in the dept SOP: the mailbox is inter-office post (CEO↔分公司) ONLY — dept reports never go there, commissioned file-drops land in the dept's own folder.

## [0.9.31] — 2026-07-20
### Added
- **`priority:` card field** (Boss's ask). Values `P0` (drop everything) · `P1` (next) · `P2`/unset (normal) — chosen so plain lexical sort orders correctly everywhere (`P0 < P1 < P2 < —`), no mapping table anywhere. First-class through the chain: cardlib FIELDS (round-trips, digest bullet, migration-safe), Boss-Board kanban (Todo/In-progress columns sort by priority tier then board order; P0 coral / P1 amber pills on card faces), Bases views (column + priority-then-id sort in the template AND the field project's live Board.base, their UI tweaks preserved). Ownership doctrine: Boss/CEO set it (card file or an Obsidian cell edit — Bases adds the property to the note); depts' only frontmatter write stays `status:` (SOP line hardened); dispatch/queue order and the branch claim order honour it (SKILL + branch skill).

## [0.9.30] — 2026-07-20
### Fixed
- **Migration no longer blocked by a pre-existing board dir.** `ensure_store` keyed "store is live" on directory existence — so a pre-staged `Board.base`, a `.DS_Store`, or a folder Obsidian created would silently veto the legacy-board migration forever. Live = *any card file present* now; migrating into an existing dir moves the built cards in file-by-file (deterministic output makes a racing double-move benign), the atomic whole-dir rename stays as the fast path. Lets a project stage its Obsidian view before its first post-0.9.28 session start.
- **Branch setup doc: the account mechanism corrected to `claude-swap run`** (session-pinned per-account profile — own `CLAUDE_CONFIG_DIR`, own keychain entry hashed from it, immune to `switch`/autoswitch on the default login; verified from claude-swap's source). `setup-token` + `CLAUDE_CODE_OAUTH_TOKEN` stays as the no-claude-swap fallback; a bare in-place `switch` documented as insufficient (running default-login sessions follow the active account on token refresh).

## [0.9.29] — 2026-07-20
### Added
- **分公司 (branch-office) lane** (Boss's direction 2026-07-20: Marketing needs claude-in-chrome on its own Claude account for capacity, so it runs as its OWN session — the account boundary is the session boundary; sync rides the 0.9.28 card store). `orchestrate.json` gains an additive `"external": ["Marketing"]` list (entries stay in `roster` — the brief file is the branch's identity). Mechanical guards keep the lane honest: the **spawn guard blocks an in-team teammate under an external dept's name** (bare or suffixed — an in-team twin would double-dispatch the lane); the **task-sync hook refuses to register an external card to the platform widget** (fill-tiers skip them; a CREATE targeting one by number/name traces to marker-misses and births nothing); the **session-start id-less flag skips external cards** (id-less BY DESIGN — the register prescription was wrong for them); the Boss-Board kanban badges external cards with a **分 pill**.
- **Mail lane** — the offices share no live channel (SendMessage is team-scoped; cross-session messaging doesn't exist), so mail is markdown notes in `docs/board/mail/` (`from` · `to` · `re: "#NNN"` · `status: unread` · optional `needs_boss`, free body). **`stop_mail.py`** (rides `stop_dispatch`) makes noticing mechanical: at turn end, unread mail addressed to THIS office nudges once per unread-set (capacity-sentinel pattern); identity = worktree-local `.claude/office.json` (absent → CEO, aliases ceo/boss/总部/hq). `cardlib.frontmatter()` reads any note's scalar keys.
- **`branch` skill** (「分公司上班」) — the branch session's contract: identity from `external` + the dept brief; shared state (cards · mail · reviews · BACKLOG) read/written at the MAIN checkout via `git-common-dir` piercing (the Auditor's own pattern) while product work stays in the branch worktree; claim by card-file `status:`; same hard L2 gate with **`x<NNN>` review keys** (durable number — no platform id exists); **path-scoped self-merge** (only with a `.pass`, an owned-paths-only diff, and a clean main tree — anything else mails the CEO); BACKLOG rows via the new **`orchestrate-log`** bin wrapper; Boss approvals for outward actions happen in the branch session. `reference/setup.md` = the Boss's bootstrap checklist (CLAUDE_CONFIG_DIR second account + Keychain verification · dedicated Chrome profile on the branch account · worktree + office marker · lane smoke test).
- **`templates/Board.base`** — Obsidian Bases view over the card store (verified 1.13 syntax): Active (grouped by status) · Cards · Done · Mail views; copy into `docs/board/` when a vault points at the repo. Property edits in Bases write straight to card frontmatter; the digest freshener folds them in at the next turn end.

## [0.9.28] — 2026-07-20
### Changed
- **Per-card board store** (groundwork for the Marketing 分公司 and the Obsidian-Bases board view — Boss's direction 2026-07-20). The board's truth moves from the single `docs/TaskBoard.md` into **one markdown note per card** (`docs/board/<NNN>-<slug>.md`: flat YAML frontmatter — id · name · dept · task_id · status · blocked_on · what · done-when · artifacts — plus a free prose body; `done/` and `archive/` keep retired cards, so every durable `#NNN` keeps its whole history as one file). Why: two sessions (CEO + a future branch office) edit **disjoint files** instead of racing one; Obsidian **Bases** can view the folder as a database (property edits write straight back to the cards); targeted per-card reads replace whole-board reads; per-card git history and wiki-link/backlink addressability for free. **`TaskBoard.md` stays as a generated digest** — its `## Active` section machine-rewritten from the cards on every write, everything else (title, notes, the SHIPPED block) preserved byte-for-byte — so every existing reader (boss-board kanban, capacity sentinel's `card_dept`, session-start sentinels, the Boss's glance) works unchanged, and nobody hand-edits it anymore.
- **Durable `#NNN` minted at birth** — every hook-born card now gets its project-wide number immediately (the subject's leading `#NNN` when free — the 0.9.26 card-face norm — else the next free number, `O_EXCL`-claimed so concurrent sessions can't share one); the platform `task_id` no longer ever wears the card's face. The completion records (BACKLOG task cell + shipped line) carry it as before.
### Added
- **`cardlib.py`** — the store's single module: YAML-subset frontmatter round-trip (unknown keys a human/Obsidian adds survive rewrites; multi-id prose `task_id`s keep the exactly-one-id match contract), atomic writes, digest surgery, and **lazy migration**: `ensure_store()` at any writer's entry splits a legacy board into cards (headings' `#NNN` kept as ids, unnumbered cards minted next-free, tombstones retired to `archive/`), built in a tmp dir and renamed in atomically. a live project migrates itself at its next session start — one notice line, no recruit, no hand work.
- **`stop_board_digest.py`** (rides `stop_dispatch`) — turn-end digest freshener: one mtime sweep, regen only when a card was edited outside the hook path (Obsidian property flip, a dept's status edit, the future branch session). Session start freshens too.
### Migrated
- `posttool_task_sync` (birth/fill/mirror/detach), `posttool_backlog_log` (retire→`done/` with shipped-date + sha stamped on the card), `session_start` (stale-id detach + fat-card sentinel now over card files) all write through cardlib; hooklib's single-file surgery stays for the migration path. Doctrine + templates updated (`department-sop`: edit **your card file's** status, never the digest; `orchestrate.json` template gains `"board"`).

## [0.9.27] — 2026-07-19
### Added
- **Brief frontmatter auto-migration**. At session start (lead, armed project), `briefs_autopatch` walks the roster's briefs and: **adds** any frontmatter field the shipped template carries with a literal value that the brief lacks (today: `model: sonnet` + the `disallowedTools` denylist; future template fields join automatically) — a **present field is NEVER overwritten** (a Boss-designated `model: fable` or a hand denylist adjustment is someone's decision, not drift), and a legacy `tools:` allowlist blocks the denylist-add (recruit converts those deliberately); **purges inline `#` comments** from field lines (the 0.9.18 loader bug class — found live in every the field project brief: 0.9.17-era comments riding `disallowedTools`/`model` lines, parsed as values); when every roster brief reaches schema parity it **advances `briefs_template_hash`** so the stamp flag stops prescribing /recruit for what the patch cured. One notice line when it acts; silence when clean; bodies byte-untouched; fail-open per file. `/recruit` shrinks to its true job: changing the roster. Applied live to the field project in the same session (plus the Boss-ordered judged flip its add-only contract rightly refuses: six dept pins `opus`→`sonnet`, Marketing's designated `fable` kept, experts untouched) — the field project now needs only its owed restart, no recruit.

## [0.9.26] — 2026-07-19
### Fixed
- **Tier guard reads plugin-agent pins too** (field false-positive within the hour: a param-less Registrar respawn was blocked although the Registrar's `model: haiku` pin has always been in its frontmatter — the guard only checked the PROJECT's `.claude/agents/`, and the Registrar is plugin-scope). `brief_model` now falls back to the plugin's own `agents/` dir, project pin winning when both exist. The block did prove the guard fires exactly where the Boss needed it — at spawn time, pre-config — it was just one directory short.
- **Hook-born cards wear the project number as their face** (field report: In-progress cards showing pill `#46` with "#151 · REDEEM-BUTTON-RED…" demoted into the name — not a render bug and not the task tools: the card was BORN that way. When no hand card exists to fill, the birth hook headed the fresh card with the platform id and left the subject's `#151` inside the text, so the coral pill honestly wore the session id). `_card_md` now promotes the subject's leading `#NNN` into the heading slot — but only when **no existing card claims that number** (a second card wearing a claimed face would make the durable id ambiguous; ambiguity keeps the old platform-id shape). The replay-dedup check matches normalised (the heading no longer byte-contains the subject). Done-column proof the rest of the chain already worked: shipped rows rendered `#146` `#41` correctly.
- **Named reviewers are blocked at spawn** (field report: multiple `clock-in:Auditor` panes; the team config confirmed it — `L1-151` · `L2-145-146-final` · `L1-153` · `L2-151-final` sitting on the members roster: the CEO had been NAMING its Auditor invocations, turning one-shot reviewers into teammates that squat panes and linger as corpses). The spawn guard now blocks any `Agent` call combining `name:` with an Auditor/Inspector `subagent_type` (namespaced or bare) — the message says re-issue without the name, `run_in_background` if non-blocking is wanted; independence comes from the fresh instance, not a name. The lingering reviewer-members in the field get caught by the capacity sentinel as idle desks and released.
- **The unmarked-ask nudge catches "Needs you"-style trailers**. A closing line opening with `Needs you` / `需要你` / `等你` now counts as a trailing ask unless it declares nothing needed ("Needs you: nothing"); the nudge text covers the benign case (items already open on the board → end the turn again unchanged, one cheap iteration). This is the general answer to the CEO's reply-shape habit colliding with board doctrine: the prose trailer stays legal as TRANSPORT — the nudge only fires when the register never got the ask.
- **Dept tier defaults to sonnet MECHANICALLY — the per-spawn param discipline is retired**. Two root causes found. ① The dept template's frontmatter pinned `model: opus` (the parity-era roster pin), so every param-less spawn came up opus by the file, not by accident. ② The tier guard DID fire at spawn time (PreToolUse, not session start) — but it sat **behind the team-config check, and the team config does not exist until the first teammate spawn completes**, so the 上岗 batch (exactly the spawns that matter) escaped it every session. Now: the template pins **`model: sonnet`** — a param-less spawn IS the default, mechanically; a **Boss-designated tier** is pinned in that dept's brief at recruit (e.g. Marketing `fable`); an explicit `model:` on the call still overrides for a one-off. The guard is reordered ahead of the config dependency and only blocks a Fable CEO's param-less spawn when the brief carries **no** pin (a pre-0.9.26 brief; the message names the /recruit cure). The `briefs_template_hash` sentinel flags stale briefs at session start — one /recruit upgrade pass migrates a project. Doctrine: model-routing table (head = sonnet default, pinned at recruit) · brain-regime (no per-spawn param needed) · SKILL §2.5 · recruit step 3.

## [0.9.25] — 2026-07-19
### Fixed
- **Liveness was keyed on a busy-flag — both pane guards watched the wrong teammates**. The postmortem's deepest find: `members[].isActive` is a BUSY-flag, not liveness — a field capture proved it (a demonstrably responsive Registrar sat `isActive:false` between commands). The spawn-collision guard (0.9.7) therefore passed every respawn onto an IDLE live handle (accidental-supersede suffixes survived the guard built to stop them), and the lingering-pane sentinel skipped every idle taskless teammate — precisely the panes it exists to flag — which is why it never fired. Both now judge liveness by **presence in `members[]`** (a clean shutdown removes the entry; alive-or-zombie both deserve the shutdown-first flow). The guard is also **lane-aware** (Boss's rule): an **explicitly suffixed** spawn matching no live member exactly is a deliberate second lane of the same dept (elastic capacity on file-disjoint cards) and passes; a bare-name respawn over a live handle (the accidental supersede) and any exact-name collision still block. Each lane is ASSIGNed by its exact handle and judged idle on its own (the capacity sentinel matches owners exactly — a busy Frontend never hides an idle Frontend-2). Doctrine in teammates.md + SKILL §7.
- **The queue was mechanically empty: designation never reached the widget.** Every pending card in the field store sat `owner:None` — the "designated to Backend-IO" the Boss saw lived only in TaskBoard `dept:` prose, which `CLAIM` cannot see, so idle desks had nothing claimable while the board read as fully assigned. SKILL §2.4 now states it flatly: designation = the widget `owner` field, nothing else.
### Added
- **Capacity sentinel** (`stop_capacity.py`, lead Stop via the dispatcher) — the mid-session enforcement doctrine alone kept failing to be (third field strike; the parked design, unparked and extended by the postmortem). At each lead turn end, reconciles the roster against the platform task store: **idle desk + unblocked pending cards** → assign/dispatch or release · **pending card owner:None whose TaskBoard card names a live desk** → prose-designated, unclaimable — ASSIGN · **ASSIGNed queues with no live Registrar** → respawn the claim desk · **idle desk, nothing pending** → release the pane. Zero tokens when healthy; one block per state-signature (acting or state movement re-arms, ignoring stays silent); boss-in-pane depts never counted idle; widget-gated sessions silent; fail-open throughout. 12 new tests.
### Changed
- **The task-widget model gate LIFTED** — probed live 2026-07-19: a Fable 5 interactive session (the exact failing case from 07-14) loads all four task tools via ToolSearch and TaskList executes. Big-model CEOs drive the lifecycle directly again; the Registrar's CEO-proxy job is dormant, its **claim desk stands** (depts still carry no task writes by design — CLAIM remains their only path). task-widget.md rewritten accordingly, gate history kept in case it returns.

## [0.9.24] — 2026-07-19
### Added
- **The durable project `#NNN` rides every Done record, wearing a coral pill** (Boss's ask: shipped rows showed only the session-scoped platform id — `#29` is unreferenceable tomorrow, `#139` is what they and the CEO actually cite). Completion hook: `card_for` now also returns the heading's own number, and a `#NNN`-headed card ships as `date · #139 · #29 · dept · name · sha` (legacy 5-field lines unchanged, renderer handles both); the BACKLOG task cell gains the same prefix (`#139 INVITE-PDF-REORG — …`), so the durable id survives into both permanent records and is grep-able next session. Renderer: **id pills** — the project `#NNN` in a coral pill (`.pj`), the platform task_id in a neutral one (`.pt`) — on every kanban card head and on the shipped lines' leading ids; inline `#N` references in prose stay plain text. Light + dark verified on a headless-Chrome fixture (both line shapes, done-status card, in-progress card).

## [0.9.23] — 2026-07-19
### Changed
- **Path-disjoint base drift no longer voids an L2 verdict** (Boss's field report, the field project: the CEO's DECISIONS-log pushes raced dept review windows on the one master line — two reviews bounced in a row with the code never wrong, and the CEO's fix was a full master freeze across every review-to-merge stretch, queueing the Boss's rulings behind review windows). The ancestry rule ("reviewed sha sits on top of current master") is a conservative proxy for the real requirement, reviewed = shipped byte-for-byte; when the drift is **path-disjoint** — master's new commits touch no file of the branch's diff, the normal case since CEO bookkeeping (DECISIONS · board · docs) and dept-owned code are disjoint by the ownership doctrine — that requirement is provable directly: every reviewed file is byte-identical across the mechanical rebase. Doctrine now says so in all three places: **Auditor contract** (drift is judged by paths, pass on the merits + note the drift, NEVER a `.fail` for disjoint drift alone — a drift `.fail` feeds the bounce counter a phantom and can trip the circuit breaker); **SKILL §2.6** (CEO: verdict transfers, rebase + FF in one motion, `git diff --name-only` ∩ empty as the check; bookkeeping never queues behind a review window; freeze master only for overlapping drift, never as the default); **dept SOP** (a disjoint-drift bounce is not yours — flag it, don't rework). Overlapping drift keeps the strict rule: re-review or freeze.

## [0.9.22] — 2026-07-19
### Fixed
- **Collision nudge covers CLI-raised asks**. The store detection had WORKED — CEO-152 carried `collides: ["CEO-151"]` — but the 0.9.21 nudge only surfaced collisions collected from the Stop hook's own marker captures, and these asks were raised via `orchestrate-board add` (the tells: kind `discuss`, `batch: null` — markers always stamp `needs`/`info` + a batch id). Two surfaces close it: **CLI `add` prints a `COLLIDES:` warning in its own output** (the raiser is mid-turn, sees it in the Bash result, can close the old ask immediately), and the **Stop hook now reads the flag from the store** instead of the capture, so every add path gets the net; a collider closed in-turn still never fires. The cap moved to a persistent multi-key file (`.claude/collide-nudge-state`) — the 0.9.21 cap shared the single-slot ask-nudge-state with the trailing-ask nudge, which would evict it and re-nudge an ignored collision forever.
### Changed
- **Direction band: format documented**. It always had one — a short leading `LABEL:` renders as the coral head, embedded newlines are preserved, clause-opening circled digits ①…⑳ break onto their own lines, file paths are clickable — but nothing told the CEO, and the field project's live direction (ad-hoc `S1…S6` enumerators, no newlines) rendered as a wall. The grammar is now in boss-board.md with the anti-pattern named; the field project's live banner restyled in place (verbatim words, newlines + ① added) and verified on the live board.

## [0.9.21] — 2026-07-18
### Added
- **Boss Board supersede collision nudge** (Boss's field report with screenshot: CEO-143 SIGN and CEO-144 GLANCE — the same #129 sign, one revision apart — both sat open in Needs-you; the explicit-close rule alone has now failed twice, CEO-27/28 before this, so the mechanical layer parked on 07-11 is unparked). `add_entry` detects the **collision**: a new decision ask from the **same dept, same kind, about the same task** as an older still-open one — the task key is the explicit `#task` field, else **the first `#NNN` the TITLE references** (the fallback carried today's case: both asks were raised without the task linkage but led their titles with #129); no key → never flagged. The Stop hook turns the flag into a **one-time block on the raising turn, BEFORE anything supersedes** (the Boss's call — first design auto-resolved silently; they chose the raiser-in-the-loop line: "add it before it supersedes, so the CEO can handle it correctly"): re-end with `@BOSS-DONE[<old-id>]: <one-line outcome>` if the new ask replaces the old (the register closes with a real outcome, not a generic face), or end unchanged and both deliberately stay open. Guards: info and notices never; cross-kind never; **same-turn marker batches never** (one-decision-per-marker lines are separate asks — each capture stamps a batch id); a collider already closed in the same turn never fires; once per collision set. Nothing auto-resolves. Cost: one feedback line + one re-ended turn, only on an actual collision. Doctrine updated in SKILL §4 · dept SOP · boss-board.md; the explicit close stays the rule, the nudge is the net.
### Changed
- **Information column reads newest-first** (Boss's ask). Needs-you keeps its oldest-first queue order (what's waited longest never sinks); Information is a feed, so the freshest fact now sits on top. Verified light+dark on a headless-Chrome fixture (info NEWEST→OLDEST top-down, Needs-you order and counts untouched, History face shows the auto-superseded outcome).

## [0.9.20] — 2026-07-18
### Fixed
- **Task-sync join key: the human card number bridges hand cards to platform ids**. Root cause: the birth hook filled a pre-existing hand-written card only on a byte-exact subject↔name match — the field project subjects lead with the durable card number (`#130 REDEEM-MODAL-CHROME — …`) while headings read `### #130 · REDEEM-MODAL-CHROME — …`, so the match never landed. Every `task_id` stayed `—`, CREATE appended minimal duplicates (the board's own housekeeping note records retiring "hook-dup #4/#5"), completions retired the duplicate or nothing (shipped rows with dept `—`), and the real card rotted in Active with hand-journaled "DONE" prose. Now the fill matches in three tiers: exact name (historic) → **the `#NNN` the subject leads with** (fills the sole unregistered card headed `### #NNN ·`) → normalised name (separator/space/case drift); ambiguity falls through to an append, never a guess, and a registered card is never re-filled. A completion whose `task_id` matches no card now leaves a trace in `.claude/marker-misses.log` instead of silently retiring nothing. Doctrine (SKILL §2.4 + task-widget.md): a registering subject leads with its card's `#NNN`.
- **Idle-nudge false positive: post-report verification Bash no longer counts as unreported work**. `bash_readonly()` classifies a command whose every segment is inspection (`git status/log/show/diff/rev-parse/…`, `ls cat head tail grep rg find wc …`, no redirects, git global flags like `-C <path>` skipped properly) as non-work; anything unlisted still counts, and the CEO's manual prompt stays the missed-nudge fallback.
### Changed
- **Idle pings: reconcile trigger, not noise** (Boss's field report: two desks sat idle with dispatch-ready cards until they nudged the CEO themselves). The v0 line "Idle ping ≠ done ≠ reported — act only on an explicit SendMessage report" muted every ping globally, discarding the only Boss-free wake-ups the CEO gets; boss-in-pane (0.9.4) was left as a redundant second mute. Inverted: **a ping hands the CEO the turn to reconcile that desk** — report outstanding → ask for it · queued cards → let it pull (`CLAIM`) · queue empty → verify the clean boundary (report filed, `.pass` verified, work merged to the reported sha, card `completed`) then **release the pane or refill it** from dispatch-ready cards. Kept: idle never equals done — merging still needs the report + `.pass`. Boss-in-pane becomes the ONE mute (as designed); the post-pane green light now also verifies the committed sha before release. Dept SOP mirror: idle pings may draw a status ask — answer with the 4-line report. (A turn-end capacity sentinel was considered and parked: with pings live, the event and the attention arrive together; mechanise only if the field shows the CEO still missing it.)
- **Crossed-messages doctrine**. In-flight crossings are inherent to async desks and rise with live-desk count + queue-pull autonomy; the system self-corrects but each crossing cost an unstructured round-trip. Now written down (SKILL §3 + dept SOP): an instruction **names its anchor** (the report sha / message it answers); several messages from one dept arriving together → act on the newest; a dept whose newer facts contradict an instruction **replies with the correction + anchor sha instead of executing** — one correction reply, not a loop. Merges already pin to the reported sha.

## [0.9.19] — 2026-07-18
### Added
- **Board file links open in the default app** (Boss's ask: a `.md` click in the CLI opens the editor; in the panel it dumped plain text into the tab). Split click behaviour: browser-native types (png/jpg/gif/webp/pdf — mockups, marked shots) keep opening in the tab via `/file`; everything else (`.md`, logs, csv, …) now fires the new **`/open` endpoint**, which resolves the path with every `/file` guard (realpath pin under root, linked-worktree fallback, bare-name basename search) and hands the file to the OS default app (`open` / `xdg-open` / `startfile`). Security: `/open` is a side-effect endpoint, so it requires the `X-Board: 1` custom header — a cross-origin page can't send one without a CORS preflight the server never grants, killing drive-by CSRF; verified 403 without the header, 204 on valid paths (full + bare-name), 404 on traversal. The `/file` href stays on every link (right-click/middle-click = raw view); `BOARD_SKIP_LAUNCH=1` exercises routing without launching apps. All suites green.

## [0.9.18] — 2026-07-18
### Changed
- **Boss Board: Information column + structured asks** (Boss's field report, with screenshot). Two problems, one redesign of the ask surface. ① **Information ≠ decisions:** 复盘 verdicts and the CEO-directed 复盘-now flag were crowding Needs-you. The Answered column becomes **Information**: fresh info-kind rows stay visible (blue dot), resolved asks fold behind a **History** sub-header (collapsed by default, count visible, outcome-collapsed faces kept). Routing: new `@BOSS-INFO[<dept>#<id>]: <fact>` marker for any pane's FYI; the Inspector's `@BOSS[Inspector]` verdicts auto-file as info (still unfiltered — the CEO can't touch them); the tally hook's bounce_diagnose flag (CEO action, Boss reads only) files as info, while bounce_escalate and the L1-refute flag (genuine Boss decisions) stay in Needs-you; the header stamp counts only Needs-you. `orchestrate-board add --kind info` for the the Boss's own FYIs. ② **Structured asks:** the norm was one bundled essay per marker. New shape `@BOSS[<dept>#<id>]: <one-line ask> :: <detail>` — the title is the row's collapsed face (decidable at a glance), the detail renders in the expansion, and **every file path the ask mentions is extracted into its own clickable files row** under a hairline (dedup'd, same `/file` endpoint). **One decision per marker** — several needs = several marker lines, each its own row; legacy bare asks keep the old behaviour. The essay-ask sentinel now judges the TITLE only (a long detail behind `::` is legitimate) and teaches the new shape. Doctrine updated across department-sop · SKILL §4 · boss-board.md · /board command; store schema untouched (title/body split at render), so existing boards need nothing. Also rides: a prior session's uncommitted direction-band polish (pre-line whitespace + circled-digit ① line breaks + label-checklist head line). Verified: 60 board tests (+3) green; light+dark headless-Chrome renders inspected (Needs-you counts exclude info; verdict + 复盘 flag in Information; structured face shows title only; files row renders).
- **Unmarked trailing asks are now caught mechanically**. The Stop hook (`stop_boss_board`) now blocks a **lead work turn** (used tools this turn) that ends on a question (`?`/`？` on the final line) with no raise/info marker — once per prompt (state in `.claude/ask-nudge-state`), feedback carries the exact fix; re-ending the turn passes, so a rhetorical or dept-aimed question costs one cheap iteration. Pure conversational turns (锁需求 dialogue, live back-and-forth with the Boss) never trip it by construction — no tool_use, no nudge. Doctrine alongside (SKILL §4 · dept SOP · boss-board.md): **a trailing question IS an ask — prose is transport, the board is the register.** Also: legacy Inspector entries (posted as needs/discuss by pre-0.9.18 stores, like the field project's live board) now route to the Information column **by dept at render time** — live boards migrate on next poll, no store surgery. Verified: 66 board tests (+6 nudge cases); fixture board with a legacy discuss-kind verdict renders it in Information, Needs-you count unpolluted.
- **Dept work-product authoring standard**. New "Work products — naming + structure" section in `department-sop.md` (live-read doctrine → reaches every dept at next spawn, no recruit/restart), pointer from `departments.md`. Naming: **two file classes, no version suffixes ever** — living docs keep ONE stable suffix-free name updated in place (generalises the canon rule; `-v2`/`-final`/date on a living doc is a defect), event docs (reports · sweeps · audits) are `<type>-<subject>-<YYYY-MM-DD>.md`, never edited after the fact. Structure: every long file, and every Boss-facing one, carries a fixed spine with verbatim headings — `TL;DR (≤3 lines)` + `Needs Boss:` up top, then `## 结论` (numbered, one line each, evidence pointers) → `## 依据` → `## 方法` → `## 附录` — conclusion before evidence always (the Boss decides from the top ten lines), stable headings as the grep API, Boss-facing prose rules encoded (one line per paragraph, no em/en dashes, project-relative paths for board linkification), and a file never substitutes for a board ask (the ask's title and the file's TL;DR must agree).
- **Agent frontmatter: inline `#` comments removed everywhere** — field-caught on live reload: the plugin-agent loader read the Registrar's `tools:` comment as tool names (`deliberately`, `minimal`, … registered as tools). All `tools:`/`disallowedTools:` values in `agents/*.md` and `templates/department.md` are now bare lists; the rationale moved to body text/docs. Rule recorded: never put inline comments in agent frontmatter values.
### Fixed
- **Brain regime arms mechanically — the prose switch stopped being the only trigger.** Field case, twice: after a restart the Fable CEO never read `brain-regime.md` unprompted (the 3-line SKILL switch drowned in the startup wall) and dept spawns went out without the `model:"sonnet"` override, burning opus/roster tiers under a regime that mandates sonnet. Two hooks close it. ① **Session-start regime arm:** SessionStart is the one hook event whose payload carries `model` (optional per docs) — when it says Fable and the project is active, the lead injection now OPENS with one loud line: brain regime applies, read the overlay before planning/dispatching, and binding even before the read — dept spawns carry an EXPLICIT model, no code in the CEO pane. Fires on startup, resume and post-compact (every SessionStart source — exactly the restart moments the miss happened); parity sessions pay zero; model absent → silent, the prose switch stays as fallback. ② **Spawn-tier guard** (extends `pretool_spawn_guard.py`): PreToolUse carries no model field, but the transcript stamps `message.model` on every assistant line (field-verified) — tail-read 64 KB, and a Fable-CEO session blocks any NAMED teammate spawn lacking a `model:` param, with the fix in the feedback. **Only the silent omission is blocked** — any explicit tier passes, because the Boss designates per-dept tiers (field fact, the field project: Marketing runs at Fable); `brain-regime.md` now records Boss-designated tiers as first-class overrides of the sonnet default. One-shots, parity sessions, Registrar (spawns with `model:"haiku"`) all untouched; both guards fail open. Tests: spawn-guard 16 (+6), session-start 31 (+3), all suites green.

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
- **Board server: zombie reclaim · superseded self-exit · direction band redesign.** Root-causes the "board still shows old code / my direction banner isn't there" trap (field case: the field project — a 0.9.6 server survived on the derived port for two days). The stale-replace kill used the pidfile pid, which can diverge from the actual port-holder across spawn generations; the kill missed, the respawn drifted to +1, and open tabs stayed orphaned on the zombie. Respawn now reclaims the derived port from any process that *answers as this project's board* (identity-checked via `/state.json` before killing — an innocent squatter is never touched). A server whose on-disk record (version stamp · port) no longer names it now exits within ~30 s **even while polled** — previously an open tab's polling defeated the idle reaper, keeping the stale server immortal while each freshly spawned current one, unpolled, reaped itself. The direction banner became an unboxed masthead band: compass-rose kicker, statement in the panel serif with a leading `LABEL:` auto-styled as the coral head, updated-age at right. Pre-0.9.14 zombies predate the self-exit check — the reclaim path retires them on the next board touch after the plugin updates. Tests: 110 script (+2) + 117 hook, green.

## [0.9.13] — 2026-07-16
### Added
- **Boss Board, four upgrades.** ① **Direction banner** — a standing product-direction section above *On your desk*, set once on the Boss's word (`orchestrate-board direction --text "…"`, `--clear` to remove; one slot, whole-text replace); machine-rendered per poll, zero recurring tokens, hidden when unset, file paths clickable. ② **Outcome-collapsed Answered rows** — `@BOSS-DONE[<id>]: <one-line outcome>` (or `orchestrate-board done <id> --sum "…"`) records the result and the Answered row collapses to it, the full ask one click behind; un-summarised asks keep the old two-line clamp. ③ **Answered column folds by default** — header keeps count + chevron; fold state survives the per-poll re-render. ④ **Today-aware Done cap** — the 5-row cap stretches to keep every today-stamped row; overflow folds into "+N more → BACKLOG.md". Docs updated (boss-board reference · /board command · SKILL marker line). Tests: 108 script + 117 hook, green, verified against a live panel.

## [0.9.12] — 2026-07-16
### Fixed
- **Ambiguity notices no longer feed back into themselves.** An ambiguous `@BOSS-DONE[<dept>]` posted its notice as a plain open board entry, so each notice inflated the next DONE's open-ask count ('2 asks open' begat '3 asks open' listing the first notice) and a dept-level DONE could never resolve again. Notices are now flagged, excluded from resolution counts, capped at one open per dept (a fresh notice supersedes the stale one; an unchanged re-raise dedups), and swept automatically once the dept's queue resolves cleanly. Pre-0.9.12 notices lack the flag — resolve them once by hand (`/board done <id>`).
- **Task chip dedup.** The ask-row task chip rendered hook-born cards as `#14 · #14 · name · status`; `chip()` now carries the same show-each-fact-once guards as the full card renderer. Tests: +4 regressions; 220 total green.

## [0.9.11] — 2026-07-15
### Fixed
- **Stale task ids auto-detach at session start** — platform ids die with their session, and the plugin left the CEO no mechanical home for "this id is dead, re-create at dispatch", so it journaled migration state into card headings (field case, the field project: panel titles like `#— (session-1 id retired; re-CREATE at dispatch)` — NOT the Registrar's doing, it proxies faithfully). Now the session-start hook detaches any exactly-one-id card whose id is absent from this session's task store (`task_id` → `—`, field surgery only, prose untouched, ambiguous cards left alone), and the existing id-less flag prescribes the re-CREATE. `task-widget.md` adds the rule: never journal id-migration into card names — the `—` field IS that state.

## [0.9.10] — 2026-07-15
### Added
- **New-artefact-dir detector**. Every `scan`/`run` now mechanically counts artefact-type files (images/PDF/video) in unconfigured dirs — skipping `.git`/`node_modules`/`archive/`/asset-style dirnames and everything already configured — and prints one `hint:` line when a dir crosses the threshold (8). Detection machine, classification model (only when the hint fires: `/housekeep` judges working-artefacts vs product-assets and proposes the config entry), decision Boss. Recurring runs stay zero-token.

## [0.9.9] — 2026-07-15
### Added
- **Housekeeping: model at the edges, machine in the loop** (Boss's design point). Ad-hoc sweeps: `orchestrate-housekeep run --path <dir-in-project> [--days N]` — the Boss names a folder ("clean up the renders"), `/housekeep` resolves and passes it, no config needed; paths outside the project are rejected. First-run discovery: in a project with no `housekeeping` config and no `docs/mockups`, `/housekeep` now instructs one turn of judgment — find the artefact-accumulating dirs, propose, write the config on the Boss's OK — after which every run and nudge is pure machine again.

## [0.9.8] — 2026-07-15
### Added
- **Timed housekeeping** (`orchestrate-housekeep` + `/housekeep` + a session-start nudge). Field cause: visual working artefacts — the Boss's marked screenshots in, dept-rendered mockups out — are load-bearing while their card is open and clutter after the round ships (~10 MB/day observed in the field project's `docs/mockups/`). The sweep is **archive-only** (`run` moves stale files to `<dir>/archive/YYYY-MM/`, subfolders preserved; deletion exists only as the explicit Boss-run `prune --days N` over archives) and **reference-safe by construction** (anything named on an Active card, an open Boss-Board ask, `CANON.md` or the SoT never moves, whatever its age — the *Recently shipped* tail deliberately doesn't protect). Dirs configurable via `orchestrate.json` `"housekeeping": [{"path": …, "days": …}]`, defaulting to `docs/mockups` at 14 days when that dir exists. "Timed" the plugin's way: `run` stamps `.claude/housekeep-stamp`, and session start nudges one line when candidates exist and the stamp is a week old — zero tokens when clean. Also sweeps plugin residue (idle-nudge state >7 d, oversized `marker-misses.log` rotated).

## [0.9.7] — 2026-07-15
### Added
- **Spawn-collision guard** (`pretool_spawn_guard.py`, PreToolUse on `Agent`): spawning a teammate whose base handle already has a LIVE member in this session's team is blocked with the fix in the feedback (wait for termination · re-task via SendMessage · or suffix deliberately and void the predecessor). Field case (the field project, same day the brain regime went live): a released opus dept was respawned at sonnet while 6 minutes into a thinking turn — a shutdown request is processed only at turn end, so the name was still held, `Backend-Engine-2` was minted, and the predecessor kept burning opus on a reassigned task. The guard fires BEFORE the duplicate exists. Only named spawns are judged (one-shots pass); liveness read fail-open from the team config's `members[].isActive`.
- **Lingering-pane sentinel** (session start, lead audience only): live teammates holding no open task are flagged one line each — release or dispatch — with the Registrar, boss-in-pane-marked depts, and suffixed-owner matches exempt. Widget-gated sessions (no platform task store) stay silent rather than guess. Zero tokens when clean, same as every sentinel.
- **Doctrine** (`teammates.md`): replacing a live teammate waits for confirmed termination before reusing the handle; truly can't wait → spawn suffixed deliberately and treat the predecessor's output as void.

## [0.9.6] — 2026-07-15
### Fixed
- **Bare filenames in asks are now clickable on the Boss Board.** Field case (the field project CEO-102): the CEO wrote the first render with its full path and abbreviated the sibling to its bare name ("docs/mockups/a.png + b.png") — natural prose economy, but the linkifier required a `dir/` segment, so the second file wasn't clickable. Two-ended fix: the page linkifier also matches bare filenames carrying a known artifact extension (png/jpg/gif/webp/pdf/svg/md/txt/csv/json/log/html/yaml/toml — an allowlist so version numbers, dates, domains and `GB/T 7714`-style prose never link), and the `/file` endpoint resolves a bare name by basename search across the main checkout and its linked worktrees (main wins; within a root the newest match wins, since an ask points at the render just produced). Hidden dirs and dependency trees are pruned from the search; every hit still passes the realpath-under-root symlink guard and the viewable-types whitelist.

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
- **Tombstone cards garbled the panel's Todo column.** Field case (the field project): during the
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
  causes (the field project CEO self-diagnosis): settled questions answered from principles
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
- **Needs-you readability for essay asks.** Field case (the field project CEO-89, 800+ chars):
  boss-board.md's decidable-ask rule (question · options · recommendation, 1–2 lines)
  is prose, and prose rots. Panel side: an expanded ask now breaks at clause
  enumerators (①…⑳ — inline references like "chain ①②③④" stay intact) and gets
  looser leading + a gap before the meta line. Root-cause side: a session-start
  sentinel flags open asks over 280 chars (id + size) with the re-raise prescription
  (`@BOSS-DONE[<old-id>]` + decidable one-liner, detail → file/card).

## [0.9.2] — 2026-07-14
### Fixed
- **Registrar reported the widget missing — its own `tools:` allowlist was starving it.**
  First real-use spawn (the field project) found no task tools on haiku, where they demonstrably exist.
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
- **Kanban parser hardened against real boards.** Field data (the field project) broke three template
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

[0.9.140]: https://github.com/Lumos221/clock-in/releases/tag/v0.9.140
