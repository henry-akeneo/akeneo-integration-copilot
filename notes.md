# Running notes — for the Loom (section 3: "how I built it / where I steered Claude Code")

## Steering moments (capture as they happen)

- **Moved API knowledge out of the agent prompt into the skill.** First
  instinct (and Claude's first drafts) put attribute-format facts in the
  agent. Redirected: agent = workflow discipline only, skill = knowledge,
  so the main thread and future agents get it too.
- **Agent `tools:` field trap.** The original plan listed
  `tools: Read, Write, Edit, Bash, Grep, Glob` — which silently *excludes
  all MCP tools*, locking the agent out of the schema discovery its own
  workflow requires. Fixed by omitting the field. (Found by checking the
  sub-agents docs before building, not by debugging.)
- **Hook re-targeted from strings to payloads.** Plan v1 matched Bash/Write
  and would have parsed shell commands. Real writes flow through the MCP
  upsert tools with structured input — so the primary gate validates
  `tool_input` against the schema cache field-by-field, and Bash gets only
  a coarse "no writes without discovery" guard. Fail closed.
- **`scope` vs `channel` naming trap.** Akeneo REST payloads use `scope`;
  the Akeneo MCP tools call the same key `channel`. The validator accepts
  both; the skill warns generated REST code must use `scope`.
- **Demo mode via SessionStart hook**, not agent guesswork: deterministic
  env-var check writes `.akeneo-mode.json` and announces the mode, so the
  failed MCP server in `/mcp` is explained before anyone worries.

## Loom script (≤5:00)

1. **0:00–0:30 — problem.** Persona: integration engineer syncing Akeneo →
   storefront/ERP. AI code invents attribute codes because PIM schema is
   instance config, not standard fields.
2. **0:30–2:00 — demo (contrast).**
   - Vanilla Claude Code: "write a product upsert" → invents
     `product_description` → would 422 (or worse, silently mangle data).
   - Plugin, demo mode fresh clone: `/akeneo-integration-copilot:scaffold-connector
     sync ecommerce-channel products to a CSV feed` → agent loads demo
     schema, verifies codes, produces script + dry-run on sample products.
   - Safety: ask for an upsert with a bogus code → hook blocks with the
     real codes listed. Failure → success → safety.
3. **2:00–3:30 — two decisions + steering.** (pick two bullets from above;
   knowledge-in-skill and payload-validating hook are the strongest)
4. **3:30–4:30 — guide walkthrough.** docs/build-your-own-plugin.md: the
   four-piece mental model, "write the skill from your review comments",
   the 80/20. Frame: this is how a customer self-serves for Salesforce/SAP.
5. **4:30–5:00 — close.** General pattern: skill=knowledge, MCP=grounding,
   hook=write gate, for any system of record.

## Todo before recording

- [ ] Fresh-clone test in a clean container (demo mode, no credentials)
- [ ] Live-mode smoke test against sandbox instance
- [ ] Record vanilla-Claude failure clip first (it's the hook of the video)
