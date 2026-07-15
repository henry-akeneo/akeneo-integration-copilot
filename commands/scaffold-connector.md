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
- Mode decided from the environment at runtime — credentials present
  means live, whatever `.akeneo-mode.json` says. In live mode the script
  fetches schema from the API itself; it never validates live data
  against a demo-sourced cache.
- A `--dry-run` flag: GETs allowed, nothing written to disk, and output
  as a preview (header + first rows + a summary line), never the full
  dataset to stdout. In demo mode, dry-run uses the plugin's
  `demo/sample-products.json` as its data source so the user sees
  concrete output immediately.
- For exports: filtering flags (`--families`, `--locales`, `--channel`,
  `--attributes`) so large catalogs aren't dumped wholesale by default.
- Credentials from env vars (`AKENEO_API_URL` or `AKENEO_BASE_URL`, plus
  client id/secret, username, password), with an explicit `--env-file`
  flag for projects that keep them in un-exported `.env` files.

When the agent finishes, show the user: the mode it ran in (live/demo),
the schema codes it verified, the dry-run command to try first, and — only
if the goal involves writing — the real-run command with a reminder that
the plugin's write-guard hook will validate payloads.
