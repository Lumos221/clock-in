#!/usr/bin/env python3
"""PreToolUse hook (Agent) — guards on teammate spawns. exit 2 = block (stderr
fed to the model); exit 0 = allow. Fail-open (any doubt → allow).

0) 分公司 lane (0.9.29): block spawning a teammate under an EXTERNAL dept's name
   (orchestrate.json `external`) — that dept runs as its own branch session; an
   in-team twin would double-dispatch the lane.
1) Spawn-collision: block spawning a teammate whose base handle already has a LIVE
   member in this session's team.
2) One card per seat, named for its card (0.9.63). Two rules:
   a dispatch handing a seat 2+ cards is split (disjoint → parallel seats in their own
   worktrees; overlapping → sequence, the rest stay queued), and a single-card dispatch
   under a BARE dept handle must be `<Dept>-<NNN>`. Per-task release was already doctrine
   (SKILL §7); naming the seat for its card is what makes SEQUENCING safe — a shutdown
   request only lands when the teammate's turn ends, so two cards through one bare name
   reopen the 2026-07-15 stranding window, while two numbered seats never collide.
   Numeric suffixes reduce to the dept, so nothing downstream changes; a SLUG would not
   (see dispatch_cards). Both rules read only ASSIGNMENT-shaped card mentions.
3) Fable approval: block ANY spawn naming `model: "fable"` unless the same call carries
   the literal `BOSS-APPROVED-FABLE`. Fable is weekly-capped and the cap is shared with
   everything else the Boss runs on it, so the tier is theirs to approve per spawn, never
   the CEO's to route (orchestrate/reference/model-routing.md). Two paths stay open and
   neither trips this: a spawn the Boss approved carries the marker, and a dept they pinned
   `model: fable` in its brief needs no param at all, so the guard never sees a value.
   Judged on EVERY spawn shape, one-shots included: any of them can name a tier, and a
   one-shot is the shape that would spend the cap with nothing named on any bill.

Field case: the CEO released an opus dept and respawned its
sonnet replacement in the same breath. A shutdown_request is a polite message a busy
teammate cannot process until its turn ends — the predecessor was 6 minutes into a
thinking turn — so the name was still held, the harness minted `Backend-Engine-2`,
and the released pane kept burning opus on a reassigned task. This guard fires at the
moment that mistake is made, BEFORE the duplicate exists.

Only teammate spawns are judged (an `Agent` call carrying `name:`); one-shots pass
untouched. Liveness = PRESENCE in the team config's members[] — a clean shutdown
removes the entry, so present = alive-or-zombie, and both deserve the
shutdown-first flow. NOT members[].isActive: that isActive
is a busy-flag (the Registrar sat isActive:false while demonstrably responsive),
so the old isActive check passed every IDLE live teammate — exactly the respawn
case this guard exists to block, and how the -2 suffix epidemic survived it."""
import sys, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import hooklib
except Exception:
    hooklib = None
try:
    import cardlib              # the L2 pre-flight reads the card the review is about
except Exception:
    cardlib = None

SUFFIX = re.compile(r"-\d+$")
# `effort=high`, `effort: high`, `EFFORT = xhigh` — one shape to write, several to
# read, because a rule that only accepts one spelling is a rule the CEO fails on a
# typo. Kept identical to posttool_seat_effort's reader: a spawn the guard accepts
# must be one the setter can act on, or the CEO is told it declared something that
# then quietly never happens.
EFFORT_RE = re.compile(r"\beffort\s*[=:]\s*(low|medium|high|xhigh|max)\b", re.I)
# The Boss's per-spawn approval for `fable`, as a verbatim string. Deliberately ONE
# spelling and deliberately shouty: a marker the CEO can produce by paraphrase is a
# marker it produces by habit, and this one is supposed to cost a round trip to write.
FABLE_OK = re.compile(r"BOSS-APPROVED-FABLE")


def base(handle):
    return SUFFIX.sub("", handle or "")


def team_config(session_id, cwd=None):
    """This project's lead team config dict, or None.

    Resolution lives in hooklib.team_key: the current id first, then the lead's `cwd`
    anchor. Keying on the id alone silently disarmed this guard on any session whose
    store key had drifted from its running id."""
    if hooklib is None:
        return None
    return hooklib.team_config(session_id, cwd)


# How a dispatch actually names the seat's OWN cards, read off three LIVE prompts rather
# than guessed (the 0.9.51 lesson): "dispatched by the CEO for card #377 (platform task
# 81)" · "read your two cards IN FULL: docs/board/361-…md (task_id 65) and
# docs/board/363-…md (task_id 67)". Both forms are ASSIGNMENT-shaped. A bare `#NNN`
# elsewhere in a spec is CONTEXT (a parent, a grounding doc, a frozen window) and must
# never be read as the seat's card — the live Frontend prompt cites #369's grounding doc
# and the Registrar's lists a whole queue.
FOR_CARD_RE = re.compile(r"for\s+(?:card\s+|task\s+)?#(\d+)\b", re.I)
BOARD_PATH_RE = re.compile(r"docs/board/(\d+)-")


def dispatch_cards(prompt):
    """Ordered, de-duplicated durable card numbers this dispatch ASSIGNS, [] if unclear.

    Union of the two assignment forms above, and deliberately NOT every `#NNN` in the
    text: a wrong prescription is worse than none, because the CEO would comply and
    misname the seat. No assignment-shaped mention → [] and both rules stay quiet."""
    text = prompt or ""
    out = []
    for n in FOR_CARD_RE.findall(text) + BOARD_PATH_RE.findall(text):
        if n not in out:
            out.append(n)
    return out


def live_collision(cfg, name):
    """The live member `name` collides with, or None.

    Lane-aware: an EXPLICITLY suffixed request
    (`Frontend-2`) that matches no live member exactly is a deliberate second
    lane of the same dept (elastic capacity on file-disjoint cards) — pass. A
    BARE-name request colliding with a live base is the accidental supersede
    (respawn without shutting the predecessor down) — block. An exact-name
    collision always blocks (the harness would auto-mint the next suffix)."""
    if not (name or "").strip():
        return None
    want_exact = name.strip().lower()
    want_base = base(name).lower()
    explicit_lane = bool(SUFFIX.search(name.strip()))
    for m in cfg.get("members", []):
        if not isinstance(m, dict):
            continue
        mname = m.get("name", "")
        if mname == "team-lead":
            continue
        # presence = liveness (isActive is a busy-flag — see module docstring)
        if mname.strip().lower() == want_exact:
            return mname
        if explicit_lane:
            continue  # distinct suffixed name = deliberate lane, base overlap intended
        if base(mname).lower() == want_base or base(str(m.get("agentType", ""))).lower() == want_base:
            return mname
    return None


def brief_model(root, name):
    """The `model:` frontmatter pin governing this handle, or ''. Checked in
    resolution order: the project brief (`.claude/agents/<base>.md`), then the
    PLUGIN's own agents/ dir — plugin-scope standing agents (Registrar: haiku)
    carry their pin there, and missing that dir false-blocked a param-less
    Registrar respawn. A pinned tier makes a param-less
    spawn benign — the frontmatter applies (template default: sonnet, 0.9.26)."""
    paths = []
    if root:
        paths.append(os.path.join(root, ".claude", "agents", "%s.md" % base(name)))
    paths.append(os.path.join(HERE, "..", "agents", "%s.md" % base(name)))
    for p in paths:
        try:
            head = open(p, encoding="utf-8").read(2048)
        except Exception:
            continue
        if not head.startswith("---"):
            continue
        fm = head.split("---", 2)[1] if head.count("---") >= 2 else head
        m = re.search(r"(?m)^model:\s*(\S+)", fm)
        if m:
            return m.group(1)
    return ""


CLASS_RE = re.compile(r"\bclass\s*[=:]\s*([A-Za-z0-9_-]+)", re.I)


def routing_row(root, dept, ti):
    """(row, class_name) from `docs/board/routing.json` for this dept, or (None, "").

    The row is the dept's `default` unless the spawn names a task class the way it
    names its other dispatch facts (`class=verdict`, same `=` as `effort=`/`nickname=`).
    An unknown class falls back to the default rather than refusing: the table is the
    CEO's own note to itself, and a typo in it must not stop the work."""
    try:
        with open(os.path.join(root, "docs", "board", "routing.json"), encoding="utf-8") as f:
            table = json.load(f)
    except Exception:
        return None, ""
    d = (table.get("departments") or {}).get(dept)
    if not isinstance(d, dict):
        return None, ""
    m = CLASS_RE.search("%s %s" % (ti.get("description") or "", ti.get("prompt") or ""))
    cls = m.group(1) if m else ""
    row = ((d.get("task_classes") or {}).get(cls)) if cls else None
    if isinstance(row, dict):
        return row, cls
    row = d.get("default")
    return (row if isinstance(row, dict) else None), ""


def org_cfg(root):
    """The active project's orchestrate.json dict, else None."""
    if not root:
        return None
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return None
    return cfg if cfg.get("active") else None


def active(root):
    return org_cfg(root) is not None



# ── L2 pre-flight ────────────────────────────────────────────────────────────────
# Roughly half of one project's review rounds were paperwork-shaped: a bounce that
# changed ZERO bytes because a contract citation was missing or the evidence was not
# attached as an artefact. The 审查官 already refuses those at its STEP 0 — but only
# after an opus subagent has been spawned, has read, and has written a `.fail`, and the
# producer has taken a round trip to fix a line it could have fixed before asking.
#
# This runs the SAME refusals before the spawn, for free. It adds NO bar the reviewer
# does not already apply, and it loosens nothing: the gate still exists, the same things
# still get refused, they just stop costing a round each. Every check fails OPEN — a
# wrong block sends the producer chasing a problem it does not have, which is worse than
# the round trip this saves.
TASK_ID_RE = re.compile(r"(?i)\btask[_ ]?id\b\D{0,12}(\d+)|\btask\s+(\d+)\b|#(\d+)\b")
EVIDENCE_RE = re.compile(r"(?im)^\s*(?:\*\*)?Evidence(?:\s*of\s*record)?(?:\*\*)?\s*[:：]\s*(.+)$")
PATHY_RE = re.compile(r"(?:docs|src|web|hooks|skills|tests?)/[\w./\-·—]+\.[A-Za-z0-9]{1,5}")


def review_preflight(root, ti):
    """Block reason for an 审查官 invocation that would be bounced on sight, else None."""
    prompt = "%s\n%s" % (ti.get("description") or "", ti.get("prompt") or "")
    if not prompt.strip():
        return None                                   # nothing to judge — fail open

    # ① The reviewer is told to STOP AND ASK when the id or the handle is missing, so an
    #    invocation without them buys a guaranteed wasted spawn and a question.
    if not TASK_ID_RE.search(prompt):
        return ("⛔ L2 pre-flight: this invocation names no task. Re-issue with the "
                "`task_id` and your handle — the 审查官 names its marker files from "
                "them and is told to ask rather than guess.")

    card = None
    if cardlib is not None:
        m = TASK_ID_RE.search(prompt)
        tid = next((g for g in m.groups() if g), None)
        try:
            bdir = os.path.join(root, "docs", "board")
            card = cardlib.find_task(cardlib.load(bdir), tid) if tid else None
        except Exception:
            card = None

    # ② A card that NAMES its evidence is judged on that artefact, not on prose about
    #    it. If the named file is not there, the bounce is certain and mechanical.
    if card is not None:
        m = EVIDENCE_RE.search(card.get("_body") or "")
        if m:
            missing = [q for q in PATHY_RE.findall(m.group(1))
                       if not os.path.exists(os.path.join(root, q))]
            if missing:
                return ("⛔ L2 pre-flight: this card's `Evidence` names %s, not on disk. "
                        "Produce it, or correct the path on the card, before inviting "
                        "the review — the reviewer judges the artefact, never prose "
                        "about it." % ", ".join("`%s`" % q for q in missing[:3]))

    # ③ WAS a contract-citation check. Dry-run against 481 real cards: it would have
    #    refused 98.8% of them. The reason is the useful part — "which contract governs
    #    this surface" is the judgment STEP 0 exists to make, not paperwork around it,
    #    and there is no signal on the card that decides it mechanically. Worse, the
    #    citation is the CEO's to write when it cuts the card, so refusing at review time
    #    bills the producer for someone else's omission — which is exactly why that
    #    round-1 bounce changed zero bytes. Left undone deliberately; a check that fires
    #    on almost everything teaches its reader to stop reading it.
    return None


def main():
    if hooklib is None:
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if data.get("tool_name", "") != "Agent":
        return
    ti_ = data.get("tool_input", {}) or {}
    name = ti_.get("name", "")
    # Fable is the Boss's to approve, one spawn at a time. Judged FIRST, and on every
    # spawn shape including one-shots — any of them can name a tier, and a one-shot is
    # the shape that would drain a weekly cap with nobody's name on it. A dept the Boss
    # pinned `model: fable` in its brief spawns param-less and never
    # reaches here — the guard reads the value on the CALL, which is the CEO's decision
    # and the only one the Boss has not already made. Inert off an armed project like every
    # other rule in this file: the doctrine this enforces is the CEO's, and outside an
    # orchestrate project there is no CEO to hold to it.
    if str(ti_.get("model") or "").strip().lower().startswith("fable") and \
            org_cfg(hooklib.find_root(data.get("cwd") or os.getcwd())) is not None and \
            not FABLE_OK.search("%s %s" % (ti_.get("description") or "",
                                           ti_.get("prompt") or "")):
        sys.stderr.write(
            "⛔ fable needs the Boss's word: this spawn names `model:\"fable\"`. Post one "
            "@BOSS ask (what you'd spawn · which bar it clears · your fallback), then "
            "carry on — run `opus` or a re-scope while they decide. Approved → re-issue "
            "with BOSS-APPROVED-FABLE. Never write that marker yourself.")
        sys.exit(2)
    if not name or name == "team-lead":
        # One-shot: no collision to guard. But an 审查官 invoked here is a review about
        # to happen, and the pre-flight refuses the ones it can see will bounce on sight.
        # It sits INSIDE the one-shot branch on purpose: a NAMED Auditor is a different,
        # worse mistake (a reviewer squatting a pane) and must hear that first, below.
        if base(str(ti_.get("subagent_type") or "").split(":")[-1]).lower() == "auditor":
            root_ = hooklib.find_root(data.get("cwd") or os.getcwd()) if hooklib else None
            if root_ and org_cfg(root_) is not None:
                try:
                    why = review_preflight(root_, ti_)
                except Exception:
                    why = None                   # fail open, always
                if why:
                    sys.stderr.write(why)
                    sys.exit(2)
        return
    root = hooklib.find_root(data.get("cwd") or os.getcwd())
    ocfg = org_cfg(root)
    if ocfg is None:
        return
    # 分公司 depts are NOT teammates: an external dept runs as its own session (own
    # account, own browser), syncing through the card store — an in-team spawn under
    # its name would double-dispatch the lane (0.9.29).
    if hooklib.is_external(ocfg, base(name)):
        sys.stderr.write(
            "⛔ 分公司 lane: '%s' is EXTERNAL (orchestrate.json `external`) and runs as "
            "its own branch session, never a teammate. Leave its cards (dept: %s) for "
            "the branch to claim; message it via docs/board/mail/. To bring it in-house, "
            "remove it from `external` first." % (name, base(name)))
        sys.exit(2)
    # The reviewers are ONE-SHOT subagents by contract — independence comes from a
    # fresh instance per invocation, and a named reviewer becomes a teammate that
    # holds a pane, lands on the members roster and lingers as a corpse (L1-151 · L2-145-146-final · L1-153 · L2-151-final all sitting in
    # the members list). Block the name, keep the invocation.
    rtype = base(str((data.get("tool_input", {}) or {}).get("subagent_type", ""))
                 .split(":")[-1]).lower()
    if rtype in ("auditor", "inspector"):
        sys.stderr.write(
            "⛔ reviewer-as-teammate: the 审查官/督察 is a ONE-SHOT subagent. Re-issue "
            "WITHOUT `name:` (keep subagent_type; add run_in_background for "
            "non-blocking). Named, it squats a pane and the members roster.")
        sys.exit(2)
    # Experts are one-shots for the same reason, plus one of their own: the teammate
    # spawn path DROPS a definition's `effort:`, so a named expert silently loses the
    # pin its file carries and runs at whatever the lead is set to. Named as a
    # teammate it also holds a pane it has no card for, which reads as a stalled dept.
    if rtype.startswith("prof_") or rtype.startswith("spec_"):
        sys.stderr.write(
            "⛔ expert-as-teammate: a Prof_/Spec_ expert is a ONE-SHOT subagent. "
            "Re-issue WITHOUT `name:` (keep subagent_type; add run_in_background for "
            "non-blocking). Named, it squats a pane with no card and loses its brief's "
            "`effort:` pin — only the subagent path honours it.")
        sys.exit(2)
    # Tier guard FIRST — it must not sit behind the team config, which does not
    # exist until the first teammate spawn completes: the 上岗 batch (exactly the
    # spawns that matter) escaped the old ordering every time (field case ×3).
    # A project brief carrying a model: pin (template default sonnet since 0.9.26)
    # makes the omission benign — the frontmatter tier applies; only a pinless
    # The routing table, on the SILENT path only. A spawn that names a model has made a
    # decision and the doctrine says an explicit tier always passes; what nobody catches
    # is the spawn that names none, inherits the brief's pin, and comes up a tier below
    # what this dept's row says the work needs — silently, and looking correct. The table
    # is the CEO's own note to itself, so this reports the ONE row in question and never
    # the table: a guard that dumps a config file makes the reader find their own line.
    ti_now = (data.get("tool_input", {}) or {})
    if not ti_now.get("model") and base(name).lower() not in ("registrar", "team-lead"):
        dept_h = base(str(ti_now.get("subagent_type") or "").split(":")[-1]) or base(name)
        row, cls = routing_row(root, dept_h, ti_now)
        pin = brief_model(root, name)
        want = str((row or {}).get("model") or "")
        if want and pin and want != pin:
            # Two facts and the parameter. Which tier this card wants is the CEO's call —
            # the table is its own standing note, not an order — so naming a value here
            # would answer the question this guard exists to make somebody ask. Saying
            # so out loud ("whichever you name", "nothing here can tell which you meant")
            # is the same mistake wearing humility: the reader is mid-dispatch and needs
            # the two numbers and the parameter, not the guard's reasoning about itself.
            sys.stderr.write(
                "⛔ routing: `%s` names no model — it opens on its brief's `%s`. "
                "routing.json routes %s%s to `%s`. Pass `model:` and it goes."
                % (name, pin, dept_h, (" class `%s`" % cls) if cls else "", want))
            sys.exit(2)
    # One card per seat, each seat named for its card.
    # The Registrar is exempt by role: its prompt carries the whole queue as context.
    if base(name).lower() not in ("registrar", "team-lead"):
        # The DEPT for the prescription comes from `subagent_type`, not the name — a CEO
        # invents task-named seats organically (`spacefix352`, `iofix338`,
        # `ioaudit362`, `fencefix359` all appear as completed-card owners on the live
        # board), and those names carry their number with no separator, so `base()` cannot
        # strip it: each reads as a dept nobody staffs, finds no agent brief, and never
        # matches a card's `dept` in a liveness check. Prescribing off `base(name)` there
        # would answer 'spacefix352-352'. The instinct is right; the shape has to be
        # `<Dept>-<NNN>` for anything downstream to follow it.
        dept = base(str((data.get("tool_input", {}) or {}).get("subagent_type", ""))
                    .split(":")[-1]) or base(name)
        cards = dispatch_cards((data.get("tool_input", {}) or {}).get("prompt", ""))
        if len(cards) > 1:
            sys.stderr.write(
                "⛔ one card per seat: this hands '%s' %d cards at once (%s). Split it — "
                "boundaries DISJOINT → one seat per card in parallel, each in its own "
                "worktree ('%s-%s', '%s-%s'); OVERLAP → this seat takes the first, the "
                "rest stay queued. A seat carrying several cards re-proposes what it "
                "already abandoned."
                % (name, len(cards), ", ".join("#" + c for c in cards),
                   dept, cards[0], dept, cards[1]))
            sys.exit(2)
        if len(cards) == 1 and not (SUFFIX.search(name.strip())
                                    and base(name).lower() == dept.lower()):
            card = cards[0]
            sys.stderr.write(
                "⛔ seat naming: this dispatch is for card #%s, so the seat is '%s-%s', "
                "not a bare '%s'. Re-issue with name:\"%s-%s\". Two card-numbered seats "
                "never collide, so the next one spawns the moment you tell this one to "
                "stop. **Digits only, never a slug** ('%s-adoptcard') — a slug reads as "
                "a dept nobody staffs: false stall alarms, no brief found."
                % (card, dept, card, name, dept, card, dept))
            sys.exit(2)
    # The effort declaration is NOT required while the setter is unwired: demanding a
    # declaration nothing acts on is friction with no payoff.
    cfg = team_config(data.get("session_id"), data.get("cwd") or "")
    if cfg is None:
        return
    hit = live_collision(cfg, name)
    if hit:
        sys.stderr.write(
            "⛔ spawn-collision: '%s' collides with the LIVE teammate '%s'. Replacing "
            "it → shut it down first (SendMessage shutdown request, lands when its turn "
            "ends) or re-task it; a respawn over a live handle strands the predecessor. "
            "A deliberate second lane → name it for its card ('%s-<NNN>') on "
            "file-disjoint work." % (name, hit, base(name)))
        sys.exit(2)
    return


if __name__ == "__main__":
    main()
