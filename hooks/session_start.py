#!/usr/bin/env python3
"""SessionStart hook — when CEO orchestration is active in this project, arm CEO mode:
inject the standing reminder, any signed 红线, and the SoT (source of truth — the
compass). Does nothing in a project without an active .claude/orchestrate.json marker.
Resolves the marker like every other hook — walk up from cwd, pierce a linked worktree
to the main checkout — so a session started in a subdirectory still arms (reads cwd
from stdin JSON; fail-open — any error → stay silent).

Loads SoT.md, NOT BACKLOG.md: SoT is the small "where we stand" compass designed to
load each session; BACKLOG is the append-only finished-task log, never auto-loaded.

Also the token-free bloat sentinel: file discipline (SoT ~15-line cap · cards are
pointers, not journals) is prose doctrine, and prose doctrine rots between one-off
housekeepings. This hook re-measures at EVERY session start and flags what's over —
zero tokens when clean, one line per violation until fixed. Detection only: never
machine-truncate CEO prose (a hook can't know which lines carry the judgement).

Same sentinel pattern over DECISIONS.md (field causes, refcheck 07-14): a tagged
[topic-key] ruling with no CANON row makes lookups grep-luck, and a recent entry
with no **Impl:** line is silent loss — implementation "queued" in prose that never
became a card, so the dead behaviour survives and re-teaches the dead design. And
tombstone TaskBoard cards (finished, hand-closed by striking the heading, no
task_id) get a DELETE prescription — the register-via-TaskCreate advice would
re-register shipped work, so a CEO rightly ignores it and the tombstones rot."""
import sys, json, os, re
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "orchestrate", "scripts"))
try:
    import hooklib, cardlib
except Exception:
    hooklib = cardlib = None
try:
    import board  # only for main_checkout (worktree piercing)
except Exception:
    board = None

SOT_MAX_LINES = 20      # doctrine says ~15; flag with a little slack
SOT_MAX_CHARS = 2000
CARD_MAX_CHARS = 1200   # a card is a pointer; past this it's become a journal
IMPL_RECENT_DAYS = 7    # only recent entries owe an **Impl:** — never spam the archive
ASK_MAX_CHARS = 280     # a decidable ask is 1–2 lines; the Boss reads a 2-line clamp


def sot_flag(text, sot_rel):
    """One-line over-cap flag for the SoT, or None when it's within cap."""
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) <= SOT_MAX_LINES and len(text) <= SOT_MAX_CHARS:
        return None
    return ("⚠ %s is %d lines / %d chars — over its ~15-line hard cap (it loads every "
            "session). Trim now: Now = 3 one-line slots; details/decisions → "
            "DECISIONS.md / CANON.md, never restated here." % (sot_rel, len(lines), len(text)))


def fat_cards_flag(tb_text):
    """One-line flag naming Active cards that outgrew a pointer, or None."""
    fat = []
    for a, b in hooklib.tb_card_spans(tb_text):
        if b - a > CARD_MAX_CHARS:
            head = tb_text[a:b].splitlines()[0][4:].strip()
            fat.append((head.split("·", 1)[0].strip() or head)[:24])
    return _fat_flag(fat)


def fat_card_files_flag(bdir):
    """Per-card-store version: measure each card FILE (fields + body — the body is
    where a journal actually accumulates; the digest only carries fields)."""
    fat = []
    for c in cardlib.load(bdir):
        try:
            if os.path.getsize(c["_path"]) > CARD_MAX_CHARS:
                fat.append("#%d" % c["id"])
        except OSError:
            pass
    return _fat_flag(fat)


def _fat_flag(fat):
    if not fat:
        return None
    return ("⚠ %d TaskBoard card(s) exceed %d chars (%s) — a card is a pointer, not a "
            "journal. Keep status to ONE line; history → DECISIONS.md / 复盘 / the dept's "
            "report, then cut the card back."
            % (len(fat), CARD_MAX_CHARS, ", ".join(fat[:5]) + ("…" if len(fat) > 5 else "")))


def decisions_flags(root, cfg):
    """Token-free discipline flags over DECISIONS.md (list of str; [] when clean/absent):
    tagged [topic-key] entries with no CANON row, and recent entries missing **Impl:**."""
    flags = []
    try:
        dec = open(os.path.join(root, cfg.get("decisions", "docs/DECISIONS.md")),
                   encoding="utf-8").read()
    except Exception:
        return flags
    try:
        canon = open(os.path.join(root, cfg.get("canon", "docs/CANON.md")),
                     encoding="utf-8").read()
    except Exception:
        canon = ""
    topics = {c.strip().strip("`").lower()
              for c in re.findall(r"(?m)^\|\s*([^|\n]+?)\s*\|", canon)}
    tagged, no_impl, today = [], [], date.today()
    for m in re.finditer(r"(?m)^##\s+([^\n]*)\n((?:(?!^##\s)[^\n]*\n?)*)", dec):
        head, body = m.group(1), m.group(2)
        km = re.search(r"\[([A-Za-z0-9][A-Za-z0-9_-]{2,})\]", head)
        if km:
            tagged.append(km.group(1))
        dm = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", head)
        if dm and "**Impl:**" not in body:
            try:
                age = (today - date(*map(int, dm.groups()))).days
            except ValueError:
                continue
            if 0 <= age <= IMPL_RECENT_DAYS:
                no_impl.append((km.group(1) if km else head[:32].strip()))
    unreg = [k for k in dict.fromkeys(tagged) if k.lower() not in topics]
    if unreg:
        flags.append(
            "⚠ %d tagged decision(s) have no CANON row (%s) — settled answers must be one "
            "lookup away, not grep luck. Register each: `@CANON[<dept>] <topic-key> → "
            "DECISIONS (affects: …)`, or `orchestrate-canon add`."
            % (len(unreg), ", ".join(unreg[:6]) + ("…" if len(unreg) > 6 else "")))
    if no_impl:
        flags.append(
            "⚠ %d recent DECISIONS entr%s no **Impl:** line (%s) — a behaviour-changing "
            "ruling names its card (`#<id>`), an explicit `parked: <why>`, or `none-needed`; "
            "implementation queued only in prose is silent loss (nothing tracks it, the dead "
            "behaviour re-teaches the dead design)."
            % (len(no_impl), "y carries" if len(no_impl) == 1 else "ies carry",
               ", ".join(no_impl[:4]) + ("…" if len(no_impl) > 4 else "")))
    return flags


def context_for(root, cfg, audience="lead", agent_name=None):
    """The injection text for an armed project (str), or None to stay silent.
    audience: "lead" = the CEO session (full text + discipline flags);
    "dept" = a teammate pane (slim: role line + redlines + SoT — the flags are CEO
    chores and would only distract/cost tokens in every dept spawn)."""
    if audience == "dept":
        parts = ["📋 CEO orchestration is active for this project. You are the teammate "
                 "%s — follow your agent brief; the CEO owns the task lifecycle."
                 % (agent_name or "",),
                 "Settled-question discipline: before stating what's allowed/designed/"
                 "settled, search the record — `orchestrate-canon get <topic>` + grep "
                 "DECISIONS.md — and answer from the log, not from principles."]
        redlines = cfg.get("redlines", [])
        if redlines:
            parts.append("Signed 红线 (need the Boss's two-key 准/驳 before editing):")
            for r in redlines:
                rp = r.get("path") if isinstance(r, dict) else r
                note = (" — %s" % r.get("note")) if isinstance(r, dict) and r.get("note") else ""
                parts.append("  - %s%s" % (rp, note))
        sot_rel = cfg.get("sot", "docs/SoT.md")
        try:
            text = open(os.path.join(root, sot_rel), encoding="utf-8").read()
            parts.append("\n— current source of truth (%s) —\n%s" % (sot_rel, text[:4000]))
        except Exception:
            pass
        return "\n".join(parts) + "\n"
    parts = ["📋 CEO orchestration mode is active for this project. You are the CEO — follow the orchestrate skill.",
             "Settled-question discipline: before stating what's allowed/designed/settled, "
             "search the record — `orchestrate-canon get <topic>` + grep DECISIONS.md — and "
             "answer from the log, not from principles."]
    redlines = cfg.get("redlines", [])
    if redlines:
        parts.append("Signed 红线 (need the Boss's two-key 准/驳 before editing):")
        for r in redlines:
            rp = r.get("path") if isinstance(r, dict) else r
            note = (" — %s" % r.get("note")) if isinstance(r, dict) and r.get("note") else ""
            parts.append("  - %s%s" % (rp, note))
    sot_rel = cfg.get("sot", "docs/SoT.md")
    sot = os.path.join(root, sot_rel)
    if os.path.exists(sot):
        try:
            text = open(sot, encoding="utf-8").read()
            parts.append("\n— current source of truth (%s) —\n%s" % (sot_rel, text[:4000]))
            flag = sot_flag(text, sot_rel)
            if flag:
                parts.append(flag)
        except Exception:
            pass
    tb = os.path.join(root, cfg.get("taskboard", "docs/TaskBoard.md"))
    try:
        bdir = cardlib.board_dir(root, cfg) if cardlib else ""
        if bdir and os.path.isdir(bdir):
            flag = fat_card_files_flag(bdir)
        elif os.path.exists(tb):
            flag = fat_cards_flag(open(tb, encoding="utf-8").read())
        else:
            flag = None
        if flag:
            parts.append(flag)
    except Exception:
        pass
    if board is not None:
        try:
            tbv = board.load_taskboard(root)
            # 分公司 cards live purely on the durable #NNN — never registered to the
            # CEO team's widget, so the register prescription would be WRONG for them
            idless = [t for t in tbv["tasks"] if not t["task_id"]
                      and not hooklib.is_external(cfg, t.get("dept"))]
            # A tombstone (finished card hand-closed by striking the heading) must NOT
            # get the register advice — re-registering shipped work is worse than the
            # rot, so the CEO learns to ignore the flag. Prescribe deletion instead.
            tomb = [t for t in idless
                    if board.TOMB_RE.search("%s %s" % (t["label"], t["name"]))]
            live = [t for t in idless if t not in tomb]
            if live:
                names = [(t["label"] or t["name"])[:24] for t in live]
                parts.append(
                    "⚠ %d Active card(s) carry no platform task_id (%s). CEO: register each "
                    "via TaskCreate — widget-born tasks stay hook-synced; hand-only cards rot. "
                    "(TaskCreate not loaded? It's deferred — ToolSearch "
                    "select:TaskCreate,TaskUpdate,TaskList,TaskGet first. Genuinely absent — "
                    "widget-gated session? Spawn the 书记处 Registrar (plugin-scope agent, "
                    "haiku teammate) and route the task lifecycle through it — reference/task-widget.md.)"
                    % (len(live), ", ".join(names[:6]) + ("…" if len(names) > 6 else "")))
            if tomb:
                names = [(t["label"] or t["name"])[:24] for t in tomb]
                parts.append(
                    "⚠ %d finished tombstone card(s) still sit in Active (%s) — closed by "
                    "striking the heading, so no hook can ever retire them. CEO: Delete the "
                    "card(s) now (history already lives in BACKLOG / Recently shipped). Close "
                    "live cards via TaskUpdate→completed — never by strikethrough."
                    % (len(tomb), ", ".join(names[:6]) + ("…" if len(names) > 6 else "")))
        except Exception:
            pass
    if board is not None:
        try:
            # A structured ask (`title :: body`) is judged on its TITLE — the body
            # legitimately carries the detail behind the click. Only the collapsed
            # face must stay decidable at a glance.
            fat = [(e["id"], len(e.get("text", "").split("::", 1)[0].strip()))
                   for e in board.board_list(root)
                   if e.get("status") == "open"
                   and len(e.get("text", "").split("::", 1)[0].strip()) > ASK_MAX_CHARS]
            if fat:
                parts.append(
                    "⚠ %d open Boss-Board ask(s) have essay faces (%s) — the Boss reads a "
                    "one-line title. Re-raise each as `<one-line ask> :: <detail>` (title = "
                    "question · options · recommendation; detail + file paths behind the "
                    "`::`) + `@BOSS-DONE[<old-id>]` in the same turn; one decision per marker."
                    % (len(fat), ", ".join("%s: %d chars" % f for f in fat[:4])
                       + ("…" if len(fat) > 4 else "")))
        except Exception:
            pass
    try:
        parts.extend(decisions_flags(root, cfg))
    except Exception:
        pass
    return "\n".join(parts) + "\n"


def detach_stale_ids(root, cfg, data):
    """Platform task ids die with their session. At (lead) session start, any card
    whose exactly-one-id task_id names a task ABSENT from this session's store is
    mechanically detached (task_id → —), so the existing id-less flag takes over and
    the CEO never journals migration state into card headings (field cause, refcheck
    2026-07-15: titles like "#— (session-1 id retired; re-CREATE at dispatch)").
    Field surgery on the per-card store (a legacy board migrates here — this runs
    before any flag reads the result); prose/multi-id task_ids untouched. Returns
    how many were detached."""
    if hooklib is None or cardlib is None:
        return 0
    sid = str(data.get("session_id") or "")
    if not sid:
        return 0
    cfg_root = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    store = os.path.join(cfg_root, "tasks", "session-%s" % sid[:8])
    try:
        bdir, _ = cardlib.ensure_store(root, cfg)
    except Exception:
        return 0
    if not bdir:
        return 0
    n = 0
    for card in cardlib.load(bdir):
        tid = cardlib.clean(card.get("task_id", ""))
        if tid.isdigit() and not os.path.exists(os.path.join(store, "%s.json" % tid)):
            try:
                cardlib.set_fields(card, task_id=cardlib.EMPTY)
                n += 1
            except Exception:
                pass
    if n:
        try:
            cardlib.regen_digest(root, cfg)
        except Exception:
            pass
    return n


def housekeep_flag(root, cfg):
    """One nudge line when stale artefacts exist and housekeeping hasn't run for
    RESIDUE_NUDGE_DAYS (cheap age-only count — `run` does the reference-safe part),
    or None. Zero tokens when clean or recently run."""
    try:
        import housekeep
    except Exception:
        return None
    try:
        age = housekeep.stamp_age_days(root)
        if age is not None and age < housekeep.RESIDUE_NUDGE_DAYS:
            return None
        n, b = housekeep.stale_quick_count(root, cfg)
        if not n:
            return None
        return ("⚠ housekeeping due: %d artefact file(s) (~%.0f MB) past retention — "
                "`orchestrate-housekeep run` archives the unreferenced ones "
                "(reference-safe, reversible; /housekeep for detail)." % (n, b / 1e6))
    except Exception:
        return None


def regime_arm(data):
    """One loud line arming the Fable brain regime (lead audience only), or None.
    SessionStart is the ONLY hook event that carries `model` (optional per docs;
    absent → None and the SKILL.md prose switch stays the fallback). Field cause
    (Boss, 2026-07-18): the prose regime switch was skipped twice after restarts —
    Fable planned under parity rules and spawned depts without the model override.
    The arm fires on startup, resume AND post-compact (every SessionStart source),
    exactly the moments the miss happened. Parity sessions cost zero tokens."""
    model = str(data.get("model") or "")
    if not model.startswith("claude-fable"):
        return None
    return ("🧠 REGIME SWITCH (mechanical): this session's model is Fable — the BRAIN REGIME "
            "applies. Read the orchestrate skill's reference/brain-regime.md BEFORE planning "
            "or dispatching anything. Binding even before you read it: dept teammates spawn "
            "with an EXPLICIT model (default model:\"sonnet\"; a Boss-designated tier passes "
            "too) and your pane holds NO code — diagnose and spec from artefacts.")


STANDING_AGENTS = ("Auditor", "Inspector", "Registrar")


def standing_shadow_flag(root):
    """One line when legacy project copies of the plugin-scope standing agents exist
    (.claude/agents/Auditor.md · Inspector.md · Registrar.md). Project scope shadows
    plugin scope, so a leftover copy pins the contract of whatever plugin version
    wrote it — silently immune to every later update. The recruit upgrade pass
    archives them (diffing for project-local drift first). None when clean."""
    found = [n for n in STANDING_AGENTS
             if os.path.exists(os.path.join(root, ".claude", "agents", "%s.md" % n))]
    if not found:
        return None
    return ("⚠ legacy standing-agent cop%s in .claude/agents/ (%s) shadow the plugin-scope "
            "version%s and pin outdated contracts. Run the /recruit upgrade pass — it diffs "
            "each for project-local drift (reported to the Boss, never dropped), then "
            "archives the cop%s under .claude/agents/archive/."
            % ("y" if len(found) == 1 else "ies", ", ".join(found),
               "" if len(found) == 1 else "s", "y" if len(found) == 1 else "ies"))


TEMPLATE = os.path.join(HERE, "..", "skills", "orchestrate", "templates", "department.md")


def _frontmatter_span(text):
    """(start, end) character span of the frontmatter BODY (between the --- fences),
    or None. end sits just before the closing fence line."""
    if not text.startswith("---"):
        return None
    close = text.find("\n---", 3)
    if close < 0:
        return None
    return text.index("\n", 0) + 1, close + 1


def _template_defaults():
    """{field: full_line} for the frontmatter fields the shipped template carries
    with LITERAL values (no <placeholder>) — the auto-patchable schema. Currently
    disallowedTools + model; future template fields join automatically."""
    try:
        text = open(TEMPLATE, encoding="utf-8").read()
        span = _frontmatter_span(text)
        out = {}
        for line in text[span[0]:span[1]].splitlines():
            m = re.match(r"([A-Za-z][A-Za-z]*):\s*(.+)", line)
            if m and "<" not in m.group(2):
                out[m.group(1)] = line
        return out
    except Exception:
        return {}


def briefs_autopatch(root, cfg):
    """Frontmatter auto-migration (Boss's order, 2026-07-19: end schema-migration
    recruits). For each roster brief, ADD any template frontmatter field the brief
    lacks (template's literal line, e.g. `model: sonnet`); NEVER overwrite a present
    field — a Boss-designated pin (`model: fable`) or a hand denylist adjustment is
    someone's decision, not drift. When every roster brief reaches schema parity,
    advance `briefs_template_hash` so the stamp flag stops prescribing /recruit —
    body drift is deliberately unflagged (identity + live-read pointer only; the
    doctrine itself is never in the brief). Returns notice lines ([] when clean).
    Fail-open per file; bodies byte-untouched."""
    defaults = _template_defaults()
    if not defaults:
        return []
    handles = [str(h) for h in (cfg.get("roster") or {})]
    if not handles:
        return []
    patched, parity = [], True
    for h in handles:
        p = os.path.join(root, ".claude", "agents", "%s.md" % h)
        try:
            text = open(p, encoding="utf-8").read()
        except Exception:
            continue  # roster entry without a file — recruit's problem, not ours
        span = _frontmatter_span(text)
        if span is None:
            parity = False
            continue
        fm = text[span[0]:span[1]]
        # purge inline comments from field lines FIRST — the loader parses comment
        # words as VALUES (the 0.9.18 frontmatter-comment bug: `tools: X # note`
        # registers "note" as a tool name; field case 2026-07-19: every refcheck
        # brief carried 0.9.17-era comments on disallowedTools/model lines)
        purged = re.sub(r"(?m)^((?:tools|disallowedTools|model):[^#\n]*?)\s+#.*$",
                        r"\1", fm)
        did_purge = purged != fm
        have = {m.group(1) for m in re.finditer(r"(?m)^([A-Za-z][A-Za-z]*):", purged)}
        missing = [f for f in defaults if f not in have]
        # a pre-0.9.17 `tools:` allowlist is a hand-adjustable surface — never add
        # the denylist next to it (recruit converts those deliberately)
        if "tools" in have and "disallowedTools" in missing:
            missing.remove("disallowedTools")
            parity = False
        if not missing and not did_purge:
            continue
        add = "".join(defaults[f] + "\n" for f in missing)
        out = text[:span[0]] + purged + add + text[span[1]:]
        try:
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(out)
            os.replace(tmp, p)
            what = ", ".join(["+%s" % f for f in missing] +
                             (["comments purged"] if did_purge else []))
            patched.append("%s (%s)" % (h, what))
        except Exception:
            parity = False
    if not patched:
        return []
    lines = ["🔧 dept briefs auto-migrated: %s — frontmatter only, bodies untouched; "
             "pins load at NEXT session start." % " · ".join(patched[:6])]
    if parity and cfg.get("briefs_template_hash"):
        try:
            import hashlib
            cur = hashlib.sha256(open(TEMPLATE, "rb").read()).hexdigest()[:12]
            cfg["briefs_template_hash"] = cur
            cfg_path = os.path.join(root, ".claude", "orchestrate.json")
            tmp = cfg_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, cfg_path)
        except Exception:
            pass
    return lines


def briefs_stamp_flag(root, cfg):
    """One line when dept briefs were generated from an older department template
    than the plugin now ships. recruit stamps `briefs_template_hash` (sha256[:12]
    of templates/department.md) into orchestrate.json at generation; this compares
    it against the template on disk. Silent when no stamp exists (pre-0.9.16
    project — regenerating its briefs is part of the same /recruit pass the shadow
    flag already prescribes) or when current. Doctrine (department-sop.md) is NOT
    stamped — depts read it live via `orchestrate-sop`, so it can't go stale."""
    stamp = str(cfg.get("briefs_template_hash") or "")
    if not stamp:
        return None
    tpl = os.path.join(HERE, "..", "skills", "orchestrate", "templates", "department.md")
    try:
        import hashlib
        cur = hashlib.sha256(open(tpl, "rb").read()).hexdigest()[:12]
    except Exception:
        return None
    if stamp == cur:
        return None
    return ("⚠ dept briefs predate the current department template (stamp %s ≠ %s) — "
            "run the /recruit upgrade pass, then restart (agent files load only at "
            "session start)." % (stamp, cur))


def pane_flags(root, data):
    """Lingering-pane sentinel (lead session only): one line naming live teammates
    that hold no open task, or [] when clean/undeterminable. Liveness = PRESENCE in
    members[] (a clean shutdown removes the entry); NOT isActive — that's a
    busy-flag (field-proven 2026-07-19: responsive Registrar at isActive:false), so
    the old check skipped every IDLE teammate, i.e. precisely the lingering panes
    this sentinel exists to flag, which is why it never fired in the field. Open
    tasks from the platform task store; boss-in-pane-marked depts and the Registrar
    are exempt. Widget-gated sessions (no task store) stay silent."""
    sid = str(data.get("session_id") or "")
    if not sid:
        return []
    cfg_root = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    try:
        team = json.load(open(os.path.join(cfg_root, "teams", "session-%s" % sid[:8],
                                           "config.json"), encoding="utf-8"))
    except Exception:
        return []
    if str(team.get("leadSessionId", "")) != sid:
        return []
    tasks_dir = os.path.join(cfg_root, "tasks", "session-%s" % sid[:8])
    try:
        names = os.listdir(tasks_dir)
    except Exception:
        return []  # no task store (widget-gated) — can't judge, stay silent
    owners = set()
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            t = json.load(open(os.path.join(tasks_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        if t.get("status") in ("pending", "in_progress") and t.get("owner"):
            owners.add(re.sub(r"-\d+$", "", str(t["owner"])).lower())
            owners.add(str(t["owner"]).lower())
    try:
        pane = json.load(open(os.path.join(root, ".claude", "boss-in-pane.json"),
                              encoding="utf-8"))
        exempt = {re.sub(r"-\d+$", "", k).lower() for k in pane}
    except Exception:
        exempt = set()
    orphans = []
    for m in team.get("members", []):
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", ""))
        b = re.sub(r"-\d+$", "", name).lower()
        if name == "team-lead" or b.startswith("registrar"):
            continue
        # presence = liveness (isActive is a busy-flag — see docstring)
        if name.lower() in owners or b in owners or b in exempt:
            continue
        orphans.append(name)
    if not orphans:
        return []
    return ["⚠ %d live teammate pane(s) hold no open task (%s) — release each "
            "(per-task lifecycle: SendMessage shutdown request) or dispatch its next "
            "card. Boss-in-pane-marked depts are exempt automatically."
            % (len(orphans), ", ".join(orphans[:6]) + ("…" if len(orphans) > 6 else ""))]


def main():
    if hooklib is None:
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    root = hooklib.find_root(data.get("cwd") or os.getcwd())
    if not root:
        return  # no marker = as if not installed
    if board is not None:
        root = board.main_checkout(root)
    try:
        cfg = json.load(open(os.path.join(root, ".claude", "orchestrate.json"), encoding="utf-8"))
    except Exception:
        return
    if not cfg.get("active"):
        return
    # Audience: teammate transcripts stamp agentName/agentSetting/teamName on every
    # line (field-verified 2026-07-15). Depts get the slim brief; the Registrar (a
    # mechanical proxy whose file says everything) gets nothing; the lead gets it all.
    audience, agent_name = "lead", None
    try:
        import stop_idle_nudge
        name, setting, team = stop_idle_nudge.identity(data.get("transcript_path") or "")
        if team and name and name != "team-lead":
            if (setting or name).split(":")[-1].startswith("Registrar"):  # plugin-scope setting is namespaced
                return
            audience, agent_name = "dept", name
    except Exception:
        pass
    store_notice = None
    if audience == "lead":
        try:
            # migrate a legacy board now (one-time, atomic), heal id collisions and
            # essay statuses left by concurrent sessions, then freshen the digest
            # after out-of-session card edits (Obsidian / the 分公司 branch session)
            _, store_notice = cardlib.ensure_store(root, cfg)
            bdir = cardlib.board_dir(root, cfg)
            if os.path.isdir(bdir):
                traces = cardlib.dedupe_ids(bdir) + cardlib.canonicalise(bdir)
                if traces:
                    hooklib.log_marker_misses(root, "board-hygiene", traces)
            if cardlib.digest_stale(root, cfg):
                cardlib.regen_digest(root, cfg)
            if board is not None:
                board.desk_mirror(root)  # Obsidian desk view fresh from session one
        except Exception:
            pass
        try:
            detach_stale_ids(root, cfg, data)  # before flags — the id-less flag reads the result
        except Exception:
            pass
    out = context_for(root, cfg, audience, agent_name)
    if audience == "lead":
        try:
            arm = regime_arm(data)
            if arm:
                out = arm + "\n\n" + (out or "")
        except Exception:
            pass
    if audience == "lead":
        try:
            flags = ([store_notice] if store_notice else []) + pane_flags(root, data)
            try:
                # auto-patch BEFORE the stamp flag: parity reached → stamp advanced
                # in cfg on disk AND in this dict → the /recruit prescription stays
                # silent for what the patch already cured
                flags = flags + briefs_autopatch(root, cfg)
            except Exception:
                pass
            for f in (standing_shadow_flag(root), briefs_stamp_flag(root, cfg),
                      housekeep_flag(root, cfg)):
                if f:
                    flags = flags + [f]
            if flags:
                out = (out or "") + "\n".join(flags) + "\n"
        except Exception:
            pass
    if out:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
