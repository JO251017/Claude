---
name: ship
description: End-to-end workflow for a change to this reminder app - clarify, plan, implement, review, browser-verify, commit, push and open a draft PR. Use when the user asks to add, fix or change a feature ("추가해줘", "고쳐줘", "바꿔줘") or types /ship.
---

# Ship a change

1. **Clarify once.** If an answer would change the result (e.g. what "earliest" means), ask one question; otherwise state the assumption in one line and go.
2. **Plan.** For multi-file or behavior changes, show a 3-5 line plan (files, data-format impact). One-line fixes skip this.
3. **Pick tools** from the AGENTS.md routing table (e.g. ui-ux-pro-max for a new look, unslop to polish UI).
4. **Implement** with small edits; keep saved data compatible and the UI in Korean. Run `node --check app.js`.
5. **Review and verify in parallel:** launch the `code-reviewer` and `qa-browser` subagents together. Fix real findings, then re-run `qa-browser` if code changed.
6. **Commit and ship:** commit with a clear message, push to the session branch, open a draft PR whose body lists what changed and which checks actually ran.
7. **Report:** result first, checks run, open decisions, one suggested next step.
