#!/usr/bin/env python3
"""Morning-brief renderer — turn a CEO status brief into a clean page and OPEN it.

For the overnight-run case: when a long unattended run finishes, the CEO fills a few
fields and the Boss gets a styled page on her screen in the morning. Input is
STRUCTURED (not free markdown) so the CEO writes a few short lines, not a document,
and the format can't drift — same discipline as the task log.

    echo '{"shipped":["v0.1 live on Vercel"],
           "queued":["China-access check"],
           "needs_boss":["pick Postgres vs SQLite"],
           "note":"all gates green"}' | python3 brief.py [--pdf | --png] [--out PATH]

Fields (all optional): project, shipped[], queued[], needs_boss[], note, date.
HTML by default; --pdf / --png render via a headless Chromium-family browser
(Chrome / Edge / Brave / Chromium / Vivaldi / Opera) if present, else fall back to
styled HTML opened in your default browser. Opens on macOS / Linux / Windows.
Output goes to a temp file unless --out is given. Degrades, never fails."""
import sys, os, json, html, subprocess, tempfile
from datetime import datetime

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font: 16px/1.6 -apple-system, "SF Pro Text", Helvetica, "PingFang SC", Arial, sans-serif;
       max-width: 720px; margin: 40px auto; padding: 0 24px; color: #1c1c1e; }
h1 { font-size: 1.8rem; margin-bottom: .1em; }
.stamp { color: #8e8e93; font-size: .85rem; margin-bottom: 1.8em; }
section { margin: 1.5em 0; }
h2 { font-size: 1.15rem; margin: 0 0 .4em; padding-bottom: .2em; border-bottom: 2px solid #e3e3e8; }
ul { margin: .3em 0; padding-left: 1.3em; }
li { margin: .25em 0; }
.needs h2 { color: #b3261e; border-color: #f3c7c3; }
.note { background: #f2f2f7; border-radius: 8px; padding: 12px 16px; color: #444; }
.empty { color: #8e8e93; font-style: italic; }
@media (prefers-color-scheme: dark) {
  body { color: #e3e3e8; background: #1c1c1e; }
  h2 { border-color: #3a3a3c; } .needs h2 { color: #ff6961; border-color: #5c2b28; }
  .note { background: #2c2c2e; color: #c7c7cc; }
}
"""


def items(lst):
    lst = lst or []
    if not lst:
        return "<p class='empty'>—</p>"
    return "<ul>" + "".join("<li>%s</li>" % html.escape(str(x)) for x in lst) + "</ul>"


def find_renderer():
    """Any Chromium-family browser renders HTML→PDF/PNG headlessly with the same
    flags — Chrome, Edge, Brave, Chromium, Vivaldi, Opera. Return the first found,
    so users aren't forced onto Chrome. (HTML output needs no browser at all.)"""
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
              "/Applications/Opera.app/Contents/MacOS/Opera"):
        if os.path.exists(p):
            return p
    import shutil
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                 "microsoft-edge", "microsoft-edge-stable", "brave-browser", "brave",
                 "vivaldi", "opera"):
        found = shutil.which(name)
        if found:
            return found
    return None


def main():
    args = sys.argv[1:]
    want_pdf = "--pdf" in args
    want_png = "--png" in args
    out_base = args[args.index("--out") + 1] if "--out" in args else None

    d = json.load(sys.stdin)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    proj = (" · " + html.escape(d["project"])) if d.get("project") else ""
    body = (
        "<h1>Morning brief%s</h1><div class='stamp'>CEO · %s</div>"
        "<section><h2>🚀 Shipped</h2>%s</section>"
        "<section><h2>⏭ Queued</h2>%s</section>"
        "<section class='needs'><h2>⚠ Needs you</h2>%s</section>"
    ) % (proj, stamp, items(d.get("shipped")), items(d.get("queued")), items(d.get("needs_boss")))
    if d.get("note"):
        body += "<section><div class='note'>%s</div></section>" % html.escape(d["note"])

    doc = ("<!doctype html><html><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width, initial-scale=1'>"
           "<title>Morning brief · %s</title><style>%s</style></head><body>%s</body></html>"
           ) % (stamp, CSS, body)

    base = out_base or os.path.join(tempfile.gettempdir(), "ceo-brief-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    htmlpath = base + ".html"
    with open(htmlpath, "w", encoding="utf-8") as f:
        f.write(doc)

    target, renderer = htmlpath, find_renderer()
    if (want_pdf or want_png) and renderer:
        url = "file://" + os.path.abspath(htmlpath)
        if want_pdf:
            target = base + ".pdf"
            cmd = [renderer, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf=" + target, url]
        else:
            target = base + ".png"
            cmd = [renderer, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=780,1100", "--screenshot=" + target, url]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        except Exception:
            target = htmlpath
            sys.stderr.write("(pdf/png render failed — opening HTML)\n")
    elif (want_pdf or want_png):
        sys.stderr.write("(no Chromium-family browser found for pdf/png — opening styled HTML in your default browser)\n")

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", target], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", target], check=False)
    except Exception:
        pass
    sys.stdout.write(target + "\n")


if __name__ == "__main__":
    main()
