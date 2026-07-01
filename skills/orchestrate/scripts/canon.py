#!/usr/bin/env python3
"""Canonical Answers — a machine-maintained registry (docs/CANON.md) of the current
authoritative file per answered question. Owning depts register via a `@CANON[..]`
marker (a Stop hook applies it); peers look up by topic instead of guessing filenames;
dependents are flagged when an answer changes. Stdlib only; degrades, never hard-fails.
See docs/superpowers/specs/2026-06-30-canonical-answers-design.md."""
import sys, os, re, subprocess
from datetime import datetime

COLS = ["topic", "dept", "file", "version", "updated", "affects", "needs-recheck"]
CANON_REL = os.path.join("docs", "CANON.md")
DECISIONS_REL = os.path.join("docs", "DECISIONS.md")

HEADER = (
    "# %s · CANON — canonical answers (read-first · machine-maintained · do not hand-edit)\n\n"
    "> Each row = the current authoritative file for one answered question.\n"
    "> Register via `@CANON[<dept>] <topic> -> <path> (affects: …)`; the CEO may correct via `orchestrate-canon`.\n"
    "> Use a cross-domain fact: `orchestrate-canon get <topic>` -> read the named file. **Never browse a peer's folder.**\n\n"
    "## ⚠ Needs re-check\n")


# ---------------------------------------------------------------- cell helpers
def parse_cell_list(s):
    s = (s or "").strip()
    if s in ("", "—", "-"):
        return []
    return [p.strip() for p in s.split(",") if p.strip() and p.strip() not in ("—", "-")]


def fmt_list(lst):
    return ", ".join(lst) if lst else "—"


# ---------------------------------------------------------------- markers
CANON_ACK_RE = re.compile(r"@CANON-ACK\[([^\]\s]+)\]\s+(\S+)")
CANON_RE = re.compile(r"@CANON\[([^\]\s]+)\]\s+(\S+)\s*(?:→|->)\s*(\S+?)\s*(?:\(affects:\s*([^)]*)\))?\s*$")


def parse_canon_markers(text):
    registers, acks = [], []
    for line in (text or "").splitlines():
        m = CANON_ACK_RE.search(line)
        if m:
            acks.append((m.group(1), m.group(2)))
            continue
        m = CANON_RE.search(line)
        if m:
            registers.append((m.group(1), m.group(2), m.group(3), parse_cell_list(m.group(4))))
    return {"registers": registers, "acks": acks}


# ---------------------------------------------------------------- table model
def find_row(rows, topic):
    for r in rows:
        if r["topic"] == topic:
            return r
    return None


def apply_set(rows, dept, topic, file, version, affects, now):
    row = find_row(rows, topic)
    if row is None:
        rows.append({"topic": topic, "dept": dept, "file": file, "version": version,
                     "updated": now, "affects": list(affects), "needs_recheck": list(affects)})
        return {"action": "created", "old_file": None}
    real_change = (row["file"] != file) or (row["version"] != version)
    if not real_change:
        return {"action": "unchanged", "old_file": None}
    old_file = row["file"] if row["file"] != file else None
    row["dept"] = dept
    if affects:
        row["affects"] = list(affects)
    row["needs_recheck"] = sorted(set(row["needs_recheck"]) | set(row["affects"]))
    row["file"] = file
    row["version"] = version
    row["updated"] = now
    return {"action": "changed", "old_file": old_file}


def apply_ack(rows, topic, dept):
    r = find_row(rows, topic)
    if r is None:
        return False
    r["needs_recheck"] = [d for d in r["needs_recheck"] if d != dept]
    return True


def apply_supersede(rows, topic):
    r = find_row(rows, topic)
    if r is None:
        return None
    rows.remove(r)
    return r


def get_file(rows, topic):
    r = find_row(rows, topic)
    return r["file"] if r else None


def list_rows(rows, dept=None):
    return [r for r in rows if dept is None or r["dept"] == dept]


# ---------------------------------------------------------------- load / render / save
def load_rows(path):
    rows = []
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        return rows
    in_table = False
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and cells[0] == "topic":          # header row
            in_table = True
            continue
        if set("".join(cells)) <= set("-: "):       # separator row
            continue
        if not in_table or len(cells) < 7:
            continue
        rows.append({"topic": cells[0], "dept": cells[1], "file": cells[2],
                     "version": cells[3], "updated": cells[4],
                     "affects": parse_cell_list(cells[5]),
                     "needs_recheck": parse_cell_list(cells[6])})
    return rows


def render(rows, project, decisions=None):
    flagged = [r for r in rows if r["needs_recheck"]]
    recheck = "\n".join("- `%s` → %s (updated %s)" % (r["topic"], ", ".join(r["needs_recheck"]), r["updated"])
                        for r in flagged) or "- none"
    body = ["| %s |" % " | ".join(COLS), "|%s|" % "|".join(["---"] * len(COLS))]
    for r in rows:
        body.append("| %s |" % " | ".join([
            r["topic"], r["dept"], r["file"], r["version"], r["updated"],
            fmt_list(r["affects"]), fmt_list(r["needs_recheck"])]))
    out = (HEADER % project) + recheck + "\n\n## Registry\n" + "\n".join(body) + "\n"
    dec_rows = [r for r in rows if r["file"] == "DECISIONS"]
    if dec_rows:
        lines = []
        for r in dec_rows:
            gist = (decisions or {}).get(r["topic"]) or "(no [%s] entry in DECISIONS.md — tag it)" % r["topic"]
            lines.append("- `%s` · %s — %s → `docs/DECISIONS.md`" % (r["topic"], r["dept"], gist))
        out += "\n## Key decisions (mirrored from DECISIONS.md · read-only)\n" + "\n".join(lines) + "\n"
    return out


def save_rows(path, rows, project):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render(rows, project))
    os.replace(tmp, path)


# ---------------------------------------------------------------- project root / IO
def project_root(start=None):
    d = os.path.abspath(start or os.getcwd())
    if os.path.isfile(d):
        d = os.path.dirname(d)
    cur = d
    while True:
        if os.path.exists(os.path.join(cur, ".claude", "orchestrate.json")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return d
        cur = parent


def canon_path(root):
    return os.path.join(root, CANON_REL)


def project_name(root):
    return os.path.basename(os.path.abspath(root))


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def git_short_sha(root, file):
    for cmd in (["git", "-C", root, "log", "-1", "--format=%h", "--", file],
                ["git", "-C", root, "rev-parse", "--short", "HEAD"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            sha = out.stdout.strip()
            if sha:
                return sha
        except Exception:
            pass
    return "—"


def decision_entry(root, topic):
    """(date, gist) of the topmost DECISIONS.md headline tagged [topic]; (None, None) if absent.
    gist = headline with the [token] and a leading 'YYYY-MM-DD ·' stripped."""
    try:
        text = open(os.path.join(root, DECISIONS_REL), encoding="utf-8").read()
    except Exception:
        return (None, None)
    tag = "[%s]" % topic
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("#") or tag not in s:
            continue
        head = s.lstrip("#").strip().replace(tag, " ")
        m = re.match(r"\s*(\d{4}-\d{2}-\d{2})[\s·:\-]*(.*)$", head)
        if m:
            return (m.group(1), re.sub(r"\s+", " ", m.group(2)).strip(" ·"))
        return (None, re.sub(r"\s+", " ", head).strip(" ·"))
    return (None, None)


def archive_file(root, file):
    src = file if os.path.isabs(file) else os.path.join(root, file)
    if not os.path.exists(src):
        return None
    arch = os.path.join(os.path.dirname(src), "archive")
    os.makedirs(arch, exist_ok=True)
    dst = os.path.join(arch, os.path.basename(src))
    os.replace(src, dst)
    return dst


# ---------------------------------------------------------------- command wrappers
def cmd_set(root, dept, topic, file, affects):
    p = canon_path(root)
    rows = load_rows(p)
    res = apply_set(rows, dept, topic, file, git_short_sha(root, file), affects, _today())
    if res["old_file"]:
        archive_file(root, res["old_file"])
    save_rows(p, rows, project_name(root))
    return res


def cmd_get(root, topic):
    return get_file(load_rows(canon_path(root)), topic)


def cmd_list(root, dept=None):
    return list_rows(load_rows(canon_path(root)), dept)


def cmd_ack(root, topic, dept):
    p = canon_path(root)
    rows = load_rows(p)
    ok = apply_ack(rows, topic, dept)
    save_rows(p, rows, project_name(root))
    return ok


def cmd_supersede(root, topic):
    p = canon_path(root)
    rows = load_rows(p)
    r = apply_supersede(rows, topic)
    if r:
        archive_file(root, r["file"])
    save_rows(p, rows, project_name(root))
    return r


def cmd_archive(root, file):
    return archive_file(root, file)


# ---------------------------------------------------------------- CLI
def _opt(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else ""
    root = project_root()
    if cmd == "set":
        res = cmd_set(root, _opt(argv, "--dept", "?"), _opt(argv, "--topic", ""),
                      _opt(argv, "--file", ""), parse_cell_list(_opt(argv, "--affects", "")))
        print("%s %s" % (res["action"], _opt(argv, "--topic", "")))
    elif cmd == "get":
        f = cmd_get(root, argv[1] if len(argv) > 1 else "")
        print(f if f else "not found")
    elif cmd == "list":
        for r in cmd_list(root, _opt(argv, "--dept")):
            flag = (" ⚠ recheck: " + ", ".join(r["needs_recheck"])) if r["needs_recheck"] else ""
            print("%s [%s] %s%s" % (r["topic"], r["dept"], r["file"], flag))
    elif cmd == "ack":
        ok = cmd_ack(root, argv[1] if len(argv) > 1 else "", _opt(argv, "--dept", "?"))
        print("ack ok" if ok else "topic not found")
    elif cmd == "supersede":
        r = cmd_supersede(root, argv[1] if len(argv) > 1 else "")
        print(("superseded " + r["topic"]) if r else "topic not found")
    elif cmd == "archive":
        dst = cmd_archive(root, argv[1] if len(argv) > 1 else "")
        print(("archived → " + dst) if dst else "file not found")
    else:
        sys.stderr.write("usage: orchestrate-canon set|get|list|ack|supersede|archive\n")


if __name__ == "__main__":
    main()
