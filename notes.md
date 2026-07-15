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

## Round 1 field test (real project, live instance) — what it taught us

- **Env vars are conventions, not standards.** Real project used
  `AKENEO_BASE_URL`; plugin expected `AKENEO_API_URL` → false demo mode
  with full credentials present. Fixed: alias accepted everywhere, banner
  explains the mismatch.
- **Any cached "what the env looked like" file eventually lies.** The
  session-start mode marker got trusted over reality. Fixed: mode is now a
  runtime function of the environment; marker demoted to hint; no marker +
  no env = fail closed.
- **Demo cache poisoned live mode — worst bug of the round.** Live run
  would have schema-diffed every product against the 2-family demo
  fixture (real PIM: 206 families / 178 attributes). Fixed: write-guard
  refuses `source: "demo"` cache when credentials are present; agent must
  rebuild live.
- **Credentials live in .env files, not exported vars.** SessionStart now
  scans shallowly for `.env` files with `AKENEO_` keys and says so;
  scaffolded scripts get an explicit `--env-file` flag (explicit beats
  implicit loading — consent matters).
- **Dry-run semantics codified**: GETs allowed, zero disk writes, preview
  output only (the first live dry-run printed a 38.9MB CSV to stdout).
- **Demo scale hides shape problems.** 3 products × 24 columns worked;
  2,125 × 285 was technically correct but unusable. Exports now default
  to filter flags, and PLAN asks "export everything or filter?".
- What held up first try at real scale: search_after pagination, 429
  backoff, MAX_PAGES bound, DISCOVER→VERIFY catching bad codes,
  resumable agent.
- **Structure upserts were ungated** (spotted in post-round review, not
  the field test): `attributes_upsert`, `families_upsert`,
  `channels_upsert` etc. mutate the *schema itself* — more dangerous than
  a bad product write, and unvalidatable against a schema cache by
  definition. Now blocked on live unless `AKENEO_ALLOW_STRUCTURE=1`;
  implemented as a data-tool *allowlist* so future MCP tools fail closed.

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
