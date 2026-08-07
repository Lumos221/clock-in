# Known issues — field reports from live orchestration

One entry per confirmed issue. Format: symptom · mechanism · impact · workaround · evidence (session/date). Remove an entry only when a fix ships (note the version).

## 1 · Stale hook-registry snapshot breaks sessions across plugin hook renames

- **Symptom:** every `Agent` tool call in an affected session fails at PreToolUse with `can't open file '.../hooks/pretool_echo_gate.py': No such file or directory`.
- **Mechanism:** a session snapshots the plugin's hook registry at session start. A plugin update that RENAMES a hook file (here `pretool_echo_gate.py` → `pretool_spawn_guard.py`) leaves every already-running session pointing at the deleted path; each subsequent Agent call hits the ghost file and is blocked.
- **Impact:** affected sessions cannot spawn ANY subagent — including their own L2 Auditor (`clock-in:Auditor`), so the review gate itself is unreachable. Long-lived sessions (external depts, overnight runs) are the exposed population.
- **Workaround:** restart the session at the next task boundary (`claude -c`); sessions started after the update are clean. Plugin side: prefer keeping old hook filenames as thin shims for one release when renaming.
- **The same snapshot has a second, quieter face: EDITING a registered hook takes effect in running sessions immediately, ADDING one does not.** The registry is snapshotted; the file behind an existing entry is read at each invocation. So a feature shipped as a *pair* — a `PreToolUse` guard that refuses, plus a new `PostToolUse` hook that performs — goes half-live in every running session: the refusal is enforced and the thing it demands never happens. Field case: a spawn was correctly blocked for not declaring an effort level, the CEO re-issued with the declaration, and the seat still came up at the lead's level because the setter was not in that session's registry. **Put new behaviour inside an already-registered hook whenever the choice exists** — that is not a style preference, it is the difference between a fix that reaches a running org and one that waits for a restart nobody can afford mid-flight. When a change genuinely must add a hook file, say so in the release note.
- **Evidence:** an external dept's session, 2026-07-29 mail (a `docs/board/mail/` note); CEO session and all dept seats spawned post-update confirmed unaffected the same day.

## 2 · `shutdown_response approve:true` does not terminate the responding teammate

- **Symptom:** a teammate replies to the lead's `shutdown_request` with a well-formed `{"type":"shutdown_response","request_id":…,"approve":true}` and then keeps running — emitting further `idle_notification`s; the roster/capacity sentinel continues listing the desk as live+idle indefinitely.
- **Mechanism:** unknown (harness-side); observed with TWO clean request/approve round-trips on distinct request_ids against the same seat, minutes apart, neither terminating the process. A different seat approved once the same evening and terminated normally, so the failure is intermittent, not systematic.
- **Impact:** ghost desks accumulate; capacity nudges re-fire on a seat that cannot be released; pane stays occupied.
- **Workaround:** none found from the lead side (re-issuing the request just collects another ineffective approve). Treat the seat as dead for planning; ignore its idle notifications; expect the pane to need manual closure.
- **Evidence:** Backend-Engine-921, 2026-07-29 (request ids `shutdown-1785318304922@Backend-Engine-921` approved, `shutdown-1785321107316@Backend-Engine-921` approved; idle notifications continued after both). Contrast: Backend-Engine-923 terminated normally on first approve the same hour.
- **Rule it out before blaming the harness:** the far commoner cause looks identical from the lead side but is ours, not the platform's — see §3. Check the seat's transcript for an actual `shutdown_response` first; no structured reply means it never approved.

## 3 · A seat that has never used `SendMessage` cannot answer a `shutdown_request`

- **Symptom:** the lead asks a seat to shut down, the seat answers "Acknowledged, shutting down." in prose, and the pane is still there minutes later, still in `members[]`, still holding its handle.
- **Mechanism:** the harness handles shutdown natively and documents the protocol — but it documents it **inside `SendMessage`'s own tool description**, and `SendMessage` is a *deferred* tool. A seat that has not yet loaded its schema can neither read the rule nor call the tool, so it does the only thing available and talks. Confirmed from a stuck seat's transcript: it replied in prose twice with no tool call at all, and when told what to do its very first action was `ToolSearch` for `SendMessage`.
- **Who is exposed:** only seats that are released without ever having reported. A clock-in 部门 reports through `SendMessage(to:"team-lead")` before release by SOP, so the tool is loaded long before the request arrives — which is why the field case in §2 sent a *well-formed* approve. Throwaway probe seats and any seat killed before its first report are the exposed population.
- **Impact:** the corpse holds the handle, so the next spawn of that dept collides or auto-mints a suffix. It reads as a *clean* release, so nobody checks.
- **Workaround:** re-ask, pasting the structured reply. That is enough — the seat loads the tool and terminates. (§2's seat cannot be cured this way; that is the distinction between the two.)
- **Evidence:** three probe seats, none of which had ever sent a message, all replied in prose and stayed alive. Re-asking the last one with the reply spelled out removed it from `members[]` within five seconds.
