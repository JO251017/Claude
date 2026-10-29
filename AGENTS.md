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
- There is no configured automated test suite or build command at present. Do not claim checks that were not run.
