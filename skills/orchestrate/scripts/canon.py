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


def render(rows, project):
    flagged = [r for r in rows if r["needs_recheck"]]
    recheck = "\n".join("- `%s` → %s (updated %s)" % (r["topic"], ", ".join(r["needs_recheck"]), r["updated"])
                        for r in flagged) or "- none"
    body = ["| %s |" % " | ".join(COLS), "|%s|" % "|".join(["---"] * len(COLS))]
    for r in rows:
        body.append("| %s |" % " | ".join([
            r["topic"], r["dept"], r["file"], r["version"], r["updated"],
            fmt_list(r["affects"]), fmt_list(r["needs_recheck"])]))
    return (HEADER % project) + recheck + "\n\n## Registry\n" + "\n".join(body) + "\n"


def save_rows(path, rows, project):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render(rows, project))
    os.replace(tmp, path)
