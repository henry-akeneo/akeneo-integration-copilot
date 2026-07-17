# akeneo-integration-copilot

**Grounds Claude Code in your live Akeneo PIM instance so generated integration code matches reality.**

## Who this is for

An **integration engineer at an enterprise retailer who maintains the sync
between Akeneo PIM and up/downstream systems** (storefront, ERP, marketplaces),
and wants to accelerate their integration development so their code understands the product schema, and adheres to Akeneo best-practices.

If you're new to this space: a PIM (Product Information Management system)
is the source of truth for product data, and its schema — attribute codes,
families, channels, locales — is **configuration unique to each instance**.
That's why generic AI assistance fails here: there is no "usual" schema to
guess, so it hallucinates one.

## What it does

| Component | Role |
|---|---|
| **Skill** (`akeneo-api`) | The knowledge: how the Akeneo API actually behaves — value formats, scoping, pagination, bulk semantics, error recovery |
| **Agent** (`akeneo-integration-engineer`) | The discipline: never generate integration code without checking the live schema first |
| **MCP server** (Akeneo's hosted MCP) | The grounding: real families, attributes, channels, locales from your live instance |
| **Hooks** (write-guard) | The guardrail: no write reaches product data with unknown attribute codes, wrong locale/scope combos, or above a bulk threshold |

```
you ──▶ /scaffold-connector "sync products to CSV"
              │
              ▼
   akeneo-integration-engineer ──▶ Akeneo MCP ──▶ your PIM (or demo fixture)
     DISCOVER→VERIFY→PLAN→BUILD→PROVE      │
              │                     .akeneo-schema-cache.json
              ▼                            │
        connector script            PreToolUse hook ──▶ blocks bad writes
```

## Try it in 5 minutes (no credentials needed)

```bash
# 1. Add this repo as a marketplace and install the plugin
claude plugin marketplace add henry-akeneo/akeneo-integration-copilot
claude plugin install akeneo-integration-copilot@akeneo-plugins

# 2. Start Claude Code in any project directory
claude
```

On session start you'll see a **DEMO mode** notice (no env vars set — the
`akeneo` MCP server showing as failed in `/mcp` is expected). Then run:

```
/akeneo-integration-copilot:scaffold-connector sync ecommerce-channel products to a CSV feed
```

What you should see: the agent loads the bundled demo schema (a small
retailer catalog — `tshirts` family with a localizable `description`,
scopable `price`, metric `weight`, multiselect `materials`), verifies every
code it uses against it, and produces a runnable script with a `--dry-run`
mode fed by `demo/sample-products.json`.

To see the guardrail fire, ask Claude to upsert a product with an invented
attribute (e.g. `product_description`) — the PreToolUse hook blocks it with
the list of real codes from the schema.

## Connect a real instance

Create an API connection in your PIM (**Connect → Connection settings →
Create**), then export:

```bash
export AKENEO_API_URL="https://yourcompany.cloud.akeneo.com"
export AKENEO_CLIENT_ID="..."
export AKENEO_CLIENT_SECRET="..."
export AKENEO_USERNAME="..."
export AKENEO_PASSWORD="..."
```

Restart Claude Code — the session banner switches to **LIVE mode**, and the
agent's schema discovery now hits your instance through
[Akeneo's hosted MCP server](https://api-prd.akeneo.com/mcp/overview.html).

Notes:

- `AKENEO_BASE_URL` is accepted as an alias for `AKENEO_API_URL` by the
  hooks and scaffolded scripts (the MCP server config itself reads
  `AKENEO_API_URL`; the session banner tells you if only the alias is set).
- Credentials sitting in an un-exported `.env` file don't count — but the
  session banner will point at any `.env` files it finds containing
  `AKENEO_` keys, and scaffolded scripts accept `--env-file`.
- Mode is re-checked from the environment at write time; a stale
  session-start marker can't force demo behavior, and the write-guard
  refuses to validate live writes against a demo-sourced schema cache.

Write-guard knobs:

- `AKENEO_BULK_THRESHOLD` — max items per write before blocking (default 100)
- `AKENEO_ALLOW_BULK=1` — permit writes above the threshold
- `AKENEO_ALLOW_STRUCTURE=1` — permit *structure* writes (attributes,
  families, channels, categories, ...) on a live instance. These mutate the
  schema itself, so they're blocked by default — payload validation can't
  protect the thing that defines the payloads. After a structure change,
  re-run discovery: the schema cache is stale.

## Design decisions

- **Knowledge lives in the skill, not the agent prompt.** The skill is
  loadable by the main thread, this agent, or any future agent; the agent
  holds only workflow discipline (discover → verify → plan → build → prove).
  First drafts naturally stuff API facts into the agent prompt — resist.
- **The hook validates payloads, not strings.** The primary gate matches
  the Akeneo MCP upsert tools, whose structured input can be checked
  attribute-by-attribute against the schema cache. Bash gets a coarser
  guard: commands that look like Akeneo REST writes are blocked unless
  schema discovery has run. The hook **fails closed** — no schema cache,
  no writes.
- **Why the hook ships at all**: the demo performs a real upsert path. If
  your workflow is read-only, delete `hooks/` and the plugin still works.
- **Demo mode** exists so a fresh clone gives the full experience in under
  five minutes with zero credentials — a SessionStart hook detects missing
  env vars and tells the agent (and you) which mode you're in.

## The general pattern

Skill = platform knowledge. MCP = live grounding. Hook = write gate. Swap
Akeneo for Salesforce, SAP, or NetSuite and the shape is identical: any
system of record whose schema is instance-specific configuration benefits
from exactly these three pieces. See
[docs/build-your-own-plugin.md](docs/build-your-own-plugin.md) for how to
build the same thing for your workflow.

## Development

```bash
python3 tests/test_validate_write.py   # hook write-guard tests
claude plugin validate .               # plugin structure validation
```
