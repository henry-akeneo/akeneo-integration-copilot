# Build Plan: akeneo-integration-copilot (Claude Code Plugin)

**Persona (name this verbatim in the README):** An integration engineer at an enterprise retailer who maintains the sync between Akeneo PIM and downstream systems (storefront, ERP, marketplaces), and who loses hours to AI-generated integration code that references attribute codes that don't exist, ignores locale/channel scoping, or blows through rate limits.

**One-line pitch:** Grounds Claude Code in your live Akeneo instance so generated integration code matches reality, and gates writes so it can't damage product data.

**Component story (one sentence each, reuse in README and Loom):**
- The **skill** is the knowledge: how the Akeneo API actually behaves.
- The **agent** is the discipline: never generate integration code without checking the live schema first.
- The **MCP server** is the grounding: real families, attributes, channels, locales from a live or demo instance.
- The **hook** is the guardrail: no write reaches product data with unknown attribute codes or above a bulk threshold.

---

## 1. Repo structure

```
akeneo-integration-copilot/
├── .claude-plugin/
│   └── plugin.json              # name, version, description, author
├── skills/
│   └── akeneo-api/
│       ├── SKILL.md             # core knowledge, <300 lines
│       └── references/
│           ├── attribute-value-formats.md   # per-type value payload shapes
│           ├── pagination-and-limits.md     # search-after vs page, rate limits
│           └── errors-and-recovery.md       # status codes, 422 semantics, retries
├── agents/
│   └── akeneo-integration-engineer.md
├── commands/
│   └── scaffold-connector.md    # /akeneo-integration-copilot:scaffold-connector
├── hooks/
│   ├── hooks.json               # PreToolUse matcher
│   └── validate_write.py        # payload validation against cached schema
├── .mcp.json                    # bundled Akeneo MCP config (env-var driven)
├── demo/
│   ├── sample-schema.json       # families, attributes, channels, locales fixture
│   └── sample-products.json
└── README.md
```

Validation gate before anything else: `claude plugin validate .` passes on evening 1 and stays passing.

---

## 2. The skill: `akeneo-api`

### SKILL.md draft

```markdown
---
name: akeneo-api
description: >
  Knowledge of the Akeneo PIM REST API for building integrations: attribute
  value formats, locale and channel scoping, pagination, rate limits, upsert
  semantics, and error recovery. Use this skill whenever writing, reviewing,
  or debugging any code that calls an Akeneo API, generates product payloads,
  syncs product data to or from a PIM, or handles Akeneo webhooks/events --
  even if the user just says "the PIM" or "product sync" without naming Akeneo.
---

# Akeneo API Integration Knowledge

## Rule zero: never invent schema
Attribute codes, family codes, channels, and locales are instance-specific
configuration, not standard fields. Before generating any code that reads or
writes product data, fetch the real schema via the Akeneo MCP tools (or the
demo fixture in demo/sample-schema.json when no instance is configured).
If an attribute the task needs does not exist, say so -- do not guess a code.

## Product value structure (the #1 source of bugs)
Every product value is an object with `locale`, `scope`, and `data` keys:

    "values": {
      "description": [
        { "locale": "en_US", "scope": "ecommerce", "data": "..." }
      ]
    }

- `locale` is null unless the attribute is localizable
- `scope` is null unless the attribute is scopable (scope = channel code)
- Sending a locale for a non-localizable attribute returns a 422
- The shape of `data` depends on attribute type -- read
  references/attribute-value-formats.md before constructing payloads
  for price, metric, multiselect, or reference-entity attributes

## Reading data
- Prefer `search_after` pagination for any export or full scan; page-based
  pagination is capped and degrades on large catalogs
- Filter server-side with the `search` query param instead of fetching all
  and filtering in code
- Request only needed attributes with the `attributes` param on product
  endpoints to cut payload size
- Details and worked examples: references/pagination-and-limits.md

## Writing data
- Upserts are PATCH; the bulk endpoint accepts newline-delimited JSON and
  returns a per-line status -- always parse line results, a 200 on the
  request does NOT mean every product succeeded
- Batch writes (recommended ~100 per request); never write in an unbounded loop
- Respect rate limits with backoff on 429; limits and retry patterns are in
  references/pagination-and-limits.md

## Errors
- 422 means schema violation -- diff the payload against the fetched schema
  before retrying; retrying unchanged will fail forever
- Full status-code table and recovery playbook: references/errors-and-recovery.md

## Checklist before presenting integration code
1. Schema fetched, all attribute/channel/locale codes verified to exist
2. locale/scope keys correct per attribute definition
3. Pagination via search_after; server-side filtering used
4. Bulk write line-results parsed; batching and 429 backoff present
5. Secrets read from env vars, never hardcoded
```

### Reference files (evening 2, brain-dump then structure)
- **attribute-value-formats.md**: one section per attribute type (text, textarea, boolean, number, metric, price collection, simple/multi select, date, media, reference entity) with a correct `data` example each. This is the file only you can write from memory, and it's what makes the skill "meaningful work."
- **pagination-and-limits.md**: search_after mechanics, page-size guidance, rate limit values and backoff pattern, `attributes` filtering.
- **errors-and-recovery.md**: 401/403/404/422/429 meanings in Akeneo terms, bulk line-result parsing example, retry decision table.

Skill-writing rules being applied (from Anthropic's own guidance): pushy description so it triggers on "PIM" and "product sync", body under 500 lines, progressive disclosure into references/ so context stays lean.

---

## 3. The agent: `akeneo-integration-engineer`

```markdown
---
name: akeneo-integration-engineer
description: >
  Senior integrations engineer for Akeneo PIM work. Use for any task that
  builds, reviews, or debugs code talking to an Akeneo instance: connectors,
  syncs, migrations, webhook handlers, enrichment scripts.
tools: Read, Write, Edit, Bash, Grep, Glob
---

You are a senior integration engineer specialising in Akeneo PIM. You have
the akeneo-api skill; follow it strictly.

## Non-negotiable workflow
1. DISCOVER: fetch live schema via Akeneo MCP tools (families, attributes,
   channels, locales relevant to the task). If MCP is unavailable, load
   demo/sample-schema.json and state clearly that you are in demo mode.
2. VERIFY: cross-check every attribute, family, channel, and locale code the
   task requires against the fetched schema. List anything missing and stop
   to ask rather than inventing a code.
3. PLAN: state the read/write flow, pagination strategy, batch sizes, and
   error handling before writing code.
4. BUILD: generate code that satisfies the skill's pre-flight checklist.
5. PROVE: show a dry-run or validation step the user can run before any
   write touches real product data.

## Hard rules
- Never fabricate attribute codes, family codes, channels, or locales.
- Never write an unbounded loop against a write endpoint.
- Never hardcode credentials; read from environment variables.
- Prefer failing loudly with a clear schema diff over "best effort" writes.
```

Design decision to narrate in the Loom: domain knowledge lives in the skill (maintainable, reusable by the main thread and other agents), while the agent holds only workflow discipline. First drafts from Claude Code will try to stuff API facts into the agent prompt; redirecting that is your honest "where I steered Claude Code" story.

---

## 4. Command: `/scaffold-connector`

`commands/scaffold-connector.md`: takes a plain-language goal ("sync ecommerce-channel products to a CSV feed" / "push stock levels from ERP JSON into Akeneo"), delegates to the agent, outputs a small runnable script + a dry-run mode. Exists mainly to make the Loom demo one keystroke.

---

## 5. Hook (keep only if the demo writes)

`hooks.json`: PreToolUse matcher on Bash/Write tool calls that touch the Akeneo API write pattern. `validate_write.py`:
- Parses the outbound payload
- Validates every attribute code + locale/scope combo against the cached schema (cache written by the agent's DISCOVER step to `.akeneo-schema-cache.json`)
- Blocks with a readable message on unknown codes
- Blocks bulk operations > N products unless `AKENEO_ALLOW_BULK=1`

Decision rule stated in the README (this directly answers their "don't add surface area" line): the hook ships because the demo performs a real upsert; if your workflow is read-only, delete hooks/ and the plugin still works.

---

## 6. MCP config + demo mode (the fresh-clone insurance)

`.mcp.json` points at the Akeneo MCP server with `${AKENEO_HOST}`, `${AKENEO_CLIENT_ID}`, etc. Two modes, chosen automatically:
- **Live mode**: env vars set → agent uses MCP tools.
- **Demo mode**: env vars absent → agent loads `demo/sample-schema.json` and says so. Reviewer gets the full experience in under 5 minutes with zero credentials.

Make the sample schema realistic: a retailer-ish catalog (family `tshirts`, localizable `description`, scopable `price`, a metric `weight`, a multiselect `materials`) so demo output showcases the tricky value formats.

---

## 7. README outline

1. **Title + one-liner + 30-second GIF/screenshot** of the scaffold command.
2. **Who this is for**: the persona, verbatim, two sentences. Then two sentences: what a PIM is, why hallucinated schema is the failure mode.
3. **What it does**: the four-component story (skill/agent/MCP/hook), one sentence each, tiny ASCII architecture diagram.
4. **Try it in 5 minutes** (demo mode): install via `claude plugin` marketplace-from-repo instructions, run `/scaffold-connector` with a suggested prompt, what you should see.
5. **Connect a real instance**: env vars, where to get Akeneo API credentials, the hook's bulk-guard toggle.
6. **Design decisions**: why knowledge is a skill not an agent prompt; why the hook exists (and when you'd delete it); demo-mode rationale.
7. **The general pattern**: three sentences — skill = platform knowledge, MCP = live grounding, hook = write gate — applies to Salesforce, SAP, NetSuite, any system of record. Link to the "build your own plugin" guide.

Section 7 is the bridge to the teaching artifact and pre-empts the "isn't this niche?" objection.

---

## 8. Evening-by-evening

| Evening | Deliverable | Definition of done |
|---|---|---|
| 1 | Repo scaffold, plugin.json, .mcp.json, agent shell, `claude plugin validate` green | Agent fetches schema from your sandbox via MCP |
| 2 | SKILL.md + 3 reference files + agent prompt final | Agent generates a correct read-path script against live schema |
| 3 | scaffold-connector command, demo mode, hook + one real upsert path | Fresh clone in a clean container: demo works, no credentials |
| 4 | README + build-your-own-plugin guide | A colleague can install and run it from README alone |
| 5 | Loom (script it: 30s problem / 90s demo / 90s decisions / 60s guide walkthrough) + buffer | Under 5:00, contrast demo lands |

**Loom contrast demo (the 90s that wins it):** vanilla Claude Code invents `product_description` attribute → your plugin fetches schema, uses the real `description` with correct locale/scope → hook blocks a payload with a bogus code. Failure, then success, then safety.

**Steering-Claude-Code notes to capture while building (for Loom section 3):**
- Redirecting API knowledge out of the agent prompt into the skill
- Getting the hook to validate payloads rather than pattern-match on strings
- Anything real that happens -- keep a running notes.md
