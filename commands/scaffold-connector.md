---
description: Scaffold a small, runnable Akeneo connector script from a plain-language goal, grounded in the real (or demo) schema, with a dry-run mode.
argument-hint: <what the connector should do, e.g. "sync ecommerce-channel products to a CSV feed">
---

Build a connector for this goal: $ARGUMENTS

Use the **akeneo-integration-engineer** agent to do the work. Pass it the
goal verbatim and require its full workflow (DISCOVER → VERIFY → PLAN →
BUILD → PROVE). Do not generate integration code in the main thread.

Requirements for the deliverable:

- A single small runnable script (Python preferred unless the goal or the
  project says otherwise) in the current project, plus a one-paragraph
  usage note.
- A `--dry-run` flag that prints what would be read/written without
  calling any write endpoint. In demo mode, dry-run should use the
  plugin's `demo/sample-products.json` as its data source so the user
  sees concrete output immediately.
- Credentials from env vars only.

When the agent finishes, show the user: the mode it ran in (live/demo),
the schema codes it verified, the dry-run command to try first, and — only
if the goal involves writing — the real-run command with a reminder that
the plugin's write-guard hook will validate payloads.
