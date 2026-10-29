---
name: static-web-maintenance
description: Make small, low-cost changes to dependency-free HTML, CSS, and JavaScript apps while preserving their behavior and user data.
---

# Static web app maintenance

Use this guidance for small browser applications that do not have a build system.

1. Inspect the existing page structure, styles, behavior, and storage format before editing.
2. Prefer browser APIs and small, local changes. Avoid introducing a framework, package manager, external service, or recurring cost for a narrow feature.
3. Preserve existing data formats and user-facing language. Treat saved and form-entered text as untrusted; use safe DOM insertion or escaping.
4. Keep controls semantic and keyboard accessible. Check unsupported browser APIs before calling them and explain any permission prompt in the UI.
5. Verify changed JavaScript with `node --check <file>`. For visible behavior, run the app locally and check the affected flow plus persistence after reload. If verification cannot be run, state that plainly.
6. Do not add or run tests unless the user asks you to verify the implementation. Do not claim a check passed unless it was actually run.
