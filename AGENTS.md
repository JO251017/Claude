# Repository guidance

## Project shape
- This repository is a small, dependency-free browser app built from `index.html`, `style.css`, and `app.js`.
- Keep changes focused and preserve the existing Korean-language interface.
- Avoid adding a framework, package manager, build pipeline, or paid service for a small feature.

## Working safely
- Read the relevant HTML, CSS, and JavaScript before changing behavior; keep existing browser storage data compatible.
- Treat reminder titles and notes as user input. Escape text inserted into HTML, or prefer DOM text APIs.
- Request browser notification permission only in a user-initiated flow where practical, and handle browsers without the Notification API.
- Preserve keyboard access, semantic controls, and visible focus states.
- Do not add dependencies unless the feature cannot reasonably be done with the platform APIs.

## Lightweight checks
- Run `node --check app.js` after JavaScript edits.
- For UI changes, open `index.html` in a browser and check adding, completing, deleting, sorting, and reloading reminders.
- `node scripts/smoke.js [screenshot-dir]` runs a Playwright browser smoke test (dev-only; needs Playwright, preinstalled in cloud sessions). It covers default time, escaping, delete, repeat, legacy data, sorting, focus and mobile layout.
- There is no build command or CI. Do not claim checks that were not run.

## Tool routing (installed plugins and skills)
The user will not remember tool names. Map plain requests to the tool below. When a request matches a row, say in one line which tool you will use (e.g. "unslop으로 점검할게요") and proceed; if the match is only likely, offer it in one line instead. Prefer these over other installed skills with similar descriptions.

| Situation (typical Korean phrasing) | Use | Do not use instead |
|---|---|---|
| Choosing a look before building UI: style, palette, fonts ("디자인 방향", "색/폰트 정해줘") | `ui-ux-pro-max:ui-ux-pro-max` | design-taste-frontend, codesign, figma skills |
| UI looks generic or AI-made; polish or review existing UI ("촌스러워", "AI 티 나", "다듬어줘") | `unslop:unslop` | design-taste-frontend |
| Diagram from a description or code: architecture, flow, ER, timeline ("구조도", "흐름도", "그려줘") | `diagram-design:diagram-design` (about $1 per diagram; say so for large ones) | figma generate_diagram, mermaid by hand |
| Text reads machine-written; same meaning, human tone ("자연스럽게", "사람이 쓴 것처럼") | `humanizer:humanizer` (worth it for longer text; skip for one or two sentences) | |
| What people said recently about a topic ("요즘 반응", "여론", "최근 이슈") | `last30days:last30days` | plain web search |
| Page is blocked, needs JS rendering, or must be crawled ("긁어와", "크롤링") | `scrapling-official` | |
| Turn a book or document folder into reusable knowledge ("이 책 학습", "문서를 스킬로") | `book-to-skill` | |
| Too much code, review for bloat ("코드 줄여", "과한지 봐줘") | `ponytail:ponytail-review` / `ponytail:ponytail-audit` | |

Common chains: new UI → ui-ux-pro-max, build, then unslop; new feature → superpowers brainstorming/plan, build, ponytail-review.

Environment limits: in cloud sessions, `last30days` needs first-run setup and outbound access to Reddit/X/YouTube, and `scrapling-official` reaches only hosts the network allows. If blocked, say so and suggest running it on the user's own machine; do not substitute made-up results.

Always-on plugins (no need to invoke): superpowers (ask and plan before building, verify before done), ponytail (smallest working code), caveman (terse wording). Caveman must not drop the conclusion, evidence, or verification status from a reply.

## Working as an agent
- Act on clear requests end to end: edit, run the checks above, commit, and report the result. Ask one question only when the answer would change the outcome.
- Before multi-file or behavior-changing work, show a short plan; for a one-line fix, just do it.
- Use subagents in parallel for independent research or searches across many files; keep edits in the main session.
- For feature or fix requests, follow the `ship` skill. Before reporting a change done, run the `code-reviewer` and `qa-browser` subagents (in parallel) and act on real findings.
- Suggest the next useful step in one line at the end (e.g. a tool from the table above), but do not start it unasked.
