# Build your own Claude Code plugin

*Written for an engineer who just tried akeneo-integration-copilot and
wants the same treatment for a different workflow in their org — a
Salesforce sync, an SAP feed, an internal deploy tool. One page, start to
working plugin.*

## The mental model (read this, skip the rest if you must)

A plugin packages up to four things. Decide what your workflow needs —
**don't add surface area to check boxes**:

| Piece | It is | Add it when |
|---|---|---|
| **Skill** (`skills/<name>/SKILL.md`) | Markdown knowledge Claude loads when relevant | There are facts about your platform Claude gets wrong from memory |
| **Agent** (`agents/<name>.md`) | A system prompt defining a disciplined workflow | The task has steps that must happen in order (e.g. *check reality before generating*) |
| **MCP config** (`.mcp.json`) | Connection to live data via tools | Correct output depends on instance-specific state |
| **Hook** (`hooks/hooks.json` + script) | A program that runs before/after tool calls | Some mistakes are too expensive to allow even once |

The pattern that made this plugin work: **skill = knowledge, agent =
discipline, MCP = grounding, hook = guardrail.** Most enterprise workflows
need the first two; add MCP when schema/state is instance-specific; add a
hook only when writes can hurt.

## Step by step

**1. Scaffold** (10 minutes)

```
my-plugin/
├── .claude-plugin/
│   ├── plugin.json        # {"name": "my-plugin", "version": "0.1.0", "description": "..."}
│   └── marketplace.json   # lets people install straight from your repo
├── skills/my-domain/SKILL.md
└── agents/my-engineer.md
```

Run `claude plugin validate .` now and keep it green after every change.

**2. Write the skill first** — it's the highest-value hour. Brain-dump the
things you correct in every AI-generated PR for your platform: payload
shapes, pagination traps, rate limits, "a 200 doesn't mean success"
gotchas. Rules that work:

- The frontmatter `description` decides when Claude loads it. Make it
  pushy: list every phrase a user might say (*"the PIM"*, *"product
  sync"*), not just the product name.
- Keep SKILL.md under ~300 lines; push detail into `references/*.md`
  files it links to (Claude reads them on demand).
- Lead with your "rule zero" — the one mistake that causes the most damage.

**3. Add the agent** — a markdown file whose body is a workflow, not a
knowledge base. Ours is five verbs: DISCOVER, VERIFY, PLAN, BUILD, PROVE.
If you find yourself writing API facts in the agent prompt, move them to
the skill. Omit the `tools:` frontmatter field unless you need to restrict
tools — **listing tools excludes MCP tools**, which bites you exactly when
your workflow depends on them.

**4. Wire MCP** if your platform has a server (many do now — check your
vendor's API docs for "MCP"). Use env-var expansion so credentials never
land in the repo:

```json
{ "mcpServers": { "vendor": { "type": "http", "url": "https://...",
    "headers": { "X-Api-Key": "${VENDOR_API_KEY}" } } } }
```

Then build a **demo mode**: a JSON fixture of realistic instance data plus
a SessionStart hook that detects missing env vars and tells the agent to
use the fixture. This is what makes your plugin installable by a colleague
in five minutes — and it's what makes your demo repeatable.

**5. Add a hook only if writes can hurt.** A PreToolUse hook is a script
that gets the tool call as JSON on stdin and can block it. Two rules from
building this one: validate **structured payloads** (MCP tool inputs), not
strings you regex out of shell commands — and **fail closed**: if the
script can't verify a write is safe, block it with a message that tells
Claude how to make it verifiable. Reference your script as
`${CLAUDE_PLUGIN_ROOT}/hooks/myscript.py` so it works wherever the plugin
is installed. Write a dozen stdin/stdout test cases (see `tests/` in this
repo for a dependency-free pattern); this is the one component where a bug
means either broken safety or blocked work.

**6. Ship it.** Push to a repo; teammates run:

```bash
claude plugin marketplace add your-org/my-plugin
claude plugin install my-plugin@<marketplace-name>
```

## The 80/20

If you only do three things: write the skill from your real review
comments, give the agent a check-reality-first workflow, and build the
demo fixture. That's 80% of the value — the rest is polish you can add
after the first teammate says "wait, this actually works."
