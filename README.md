<!-- Language switcher — restore once README.zh-CN.md is published:
     <div align="right"><strong>English</strong> · <a href="README.zh-CN.md">中文</a></div> -->

<!-- Drop a logo here when you have one: <p align="center"><img src="docs/assets/logo.png" width="120"></p> -->

<div align="center">

# 🕘 clock-in

**Smart models are the brains; cheap models are the hands.**

A strong model plans and decides; cheap, fast ones carry the work out. That's the split clock-in is built on — the **CEO and department heads run on Opus** (the brains: they plan, decide, and review), while the **staff they spawn run on Sonnet, or Haiku for pure grunt work** (the hands: they do the actual typing). You spend Opus on judgment, not on boilerplate.

[![version](https://img.shields.io/github/v/tag/Lumos221/clock-in?label=version&color=3b82f6)](CHANGELOG.md)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-d97757)](https://docs.claude.com/en/docs/claude-code)
[![Agent Teams](https://img.shields.io/badge/Agent%20Teams-required-f59e0b)](#youll-need)
[![license: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-22c55e)](#feedback)

</div>

<p align="center">
  <img src="docs/assets/boss-board.png" width="760"
       alt="A live 'Needs you' panel: the open questions from across the team that are waiting on the Boss's decision.">
</p>
<p align="center"><sub>The one place the threads that would've been dropped end up — every open question waiting on <em>your</em> call, in a single always-open panel.</sub></p>

---

## At a glance

- **You can trust "done."** Nothing is marked finished until an independent reviewer has actually checked it — the plan *and* the result.
- **Nothing settled gets forgotten.** The team keeps a shared memory of every decision and answer, so one part never contradicts another or works off stale information.
- **Nothing waiting on you slips.** Whatever needs your call surfaces in one place, instead of getting buried in the noise.
- **You steer in plain language.** Say what you want; the team plans it, does it, and reports back. You don't manage the machinery.
- **Someone independent watches the whole team** — even the manager. If something's going wrong, you hear about it directly.
- **It stays fast on long projects.** It keeps only what matters in view and leaves the rest on disk, so it doesn't bog down or lose the plot.

---

## What it is

You're the Boss. Your Claude Code session becomes a **manager** that breaks your goal into pieces and hands each to a **specialist** — engineering, testing, ops, legal, finance, docs, whatever the work needs. An **independent reviewer** checks every plan before work starts and every result before it's called done. A separate **overseer** watches the whole team — including the manager — and comes straight to you when something's off. And the team **remembers**: decisions and settled answers are kept where everyone can see them, so the work stays consistent as it grows.

<p align="center">
  <img src="docs/assets/hero.png" width="760"
       alt="An independent reviewer catches a defect that would have shipped broken output, and bounces it before it merges.">
</p>
<p align="center"><sub>The independent reviewer caught a defect that would have shipped broken output, and bounced it <em>before it merged</em>.</sub></p>

The point is **separation of powers.** Quality comes from the structure, not from trusting one model to mark its own homework. Most "multi-agent" tools are one prompt wearing different hats — this one isn't.

> [!NOTE]
> clock-in thinks bilingually — some roles carry Chinese names and the workflow has a Chinese shorthand. You never need to read them; everything works in plain English. They're flavour, not a requirement.

---

## Why I built it

My thoughts are jumpy and bursty. I start more threads than I finish, and the ones I don't write down slip away — so I lean hard on structure outside my head. And I can't leave a rough tool alone; when a structure doesn't quite work, I keep polishing it until it does. clock-in is the scaffolding I built to run AI agents without dropping threads: the checks, the shared memory, the one place where whatever needs me shows up.

Build for a mind that needs structure to stay on track, and you get something steadier for everyone. That's clock-in.

---

## What it's like to work with it

You say what you want, in plain words. The manager drafts a plan and runs it past you. Once you're happy, the specialists do the work and check each other's output — and you get a short, clear report of what changed.

Founder-mode means you're never boxed out: drop in on any specialist directly, hash something out, and it catches the manager up afterwards. You keep full control even as the work grows past what you could hold in your head.

<p align="center">
  <img src="docs/assets/loop.png" width="820"
       alt="Specialist teammates reporting their finished work up to the manager for an independent re-check.">
</p>
<p align="center"><sub>The team in motion — specialists do the work and report up, each result waiting on an independent check before it counts as done.</sub></p>

Leave it running and come back to a **one-glance summary of what shipped, what's queued, and what needs your decision** — so a long unattended run doesn't turn into an archaeology dig.

<p align="center">
  <img src="docs/assets/brief-example.png" alt="A one-glance morning brief: what shipped, what's queued, and what needs the Boss." width="620">
</p>
<p align="center"><sub>Wake up to the state of the run — shipped · queued · needs-you — instead of scrolling back through the night.</sub></p>

---

## Quick start

### You'll need

- **Claude Code with Agent Teams enabled** — the whole thing runs on teammates.
- **Python 3** — standard library only, nothing to `pip install`.
- **A git repo** (recommended) — the team commits as it goes, so you can always see and trust the history.

Turn on Agent Teams in your Claude Code `settings.json`:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

### Install

```text
/plugin marketplace add Lumos221/clock-in
/plugin install clock-in@mycompany
```

Then restart Claude Code. (Everything wires itself up on enable — no extra setup.)

### Start

Open a project and just say **"clocking in"** (or 「开始上班」). The first time, it sets up the team your project needs and asks you to restart so everything loads; after that it picks up right where you left off.

> [!TIP]
> **Skip it for small stuff.** A one-file tweak doesn't need a company — just ask Claude directly. clock-in earns its keep on multi-part work.

---

## Good to know

> [!WARNING]
> **Actively evolving.** It works — I use it daily — but expect rough edges.
>
> - **The way it works is still being refined** (see the [CHANGELOG](CHANGELOG.md) for what's changed release to release).
> - **Not yet cost-measured.** The brains/hands split keeps Opus on judgment and cheap models on the legwork, but I haven't yet measured the actual saving, your mileage may vary on different plans.
> - **Not yet battle-tested** on very large, long-running projects.

---

## Feedback

A personal experiment, shared in the hope it helps someone and gets better with other eyes. **Issues and PRs are very welcome** — especially concrete reports of where it breaks down on real work.

## Credits

Inspired by [edict](https://github.com/cft0808/edict) (Tang-dynasty 三省六部 / six ministries) and [Paul Graham's founder mode](https://paulgraham.com/foundermode.html).

## License

[MIT](LICENSE) — Lumos, 2026.
