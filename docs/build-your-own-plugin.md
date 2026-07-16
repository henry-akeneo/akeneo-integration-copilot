# Build your own Claude Code plugin

*Written for an engineer who just tried akeneo-integration-copilot and
wants the same treatment for a different workflow in their org — a
Salesforce sync, an SAP feed, an internal deploy tool. One page, start to
working plugin. Budget an afternoon.*

One thing before the mechanics: Claude Code is both the **runtime** and
the **co-author**. You build the plugin inside Claude Code, and Claude
does most of the typing. Your job at each step is the judgment call — so
every step below states the principle first, then the Claude move that
executes it.

## Three questions before you start

1. **What does Claude get wrong about your platform from memory?** → that's your **skill**
2. **What state is instance-specific — schema, config, live data?** → that's your **MCP config**
3. **What write can hurt?** → that's your **hook**

The answers map one-to-one onto the pieces below, and they're the first
thing you'll tell Claude in step 2. If an answer is "nothing", skip that
piece.

## The mental model

| Piece | It is | Add it when |
|---|---|---|
| **Skill** (`skills/<name>/SKILL.md`) | Markdown knowledge Claude loads when relevant | There are facts about your platform Claude gets wrong from memory |
| **Agent** (`agents/<name>.md`) | A system prompt defining a disciplined workflow | The task has steps that must happen in order (e.g. *check reality before generating*) |
| **MCP config** (`.mcp.json`) | Connection to live data via tools | Correct output depends on instance-specific state |
| **Hook** (`hooks/hooks.json` + script) | A program that runs before/after tool calls | Some mistakes are too expensive to allow even once |
| **Command** (`commands/<name>.md`) | A slash-command prompt that kicks off the workflow | Users need a one-line entry point (ours: `/scaffold-connector`) |

The pattern that made this plugin work: **skill = knowledge, agent =
discipline, MCP = grounding, hook = guardrail, command = front door.**
Most enterprise workflows need the first two; add MCP when schema/state
is instance-specific; add a hook only when writes can hurt.

## Step by step

**1. Scaffold**

```
my-plugin/
├── .claude-plugin/
│   ├── plugin.json        # {"name": "my-plugin", "version": "0.1.0", "description": "..."}
│   └── marketplace.json   # lets people install straight from your repo
├── skills/my-domain/SKILL.md
└── agents/my-engineer.md
```

Ask Claude to generate this, then wire your dev loop — your working
directory doubles as a marketplace:

```bash
claude plugin marketplace add ./my-plugin
claude plugin install my-plugin@my-marketplace   # @<the "name" in marketplace.json>
```

Restart Claude Code and your plugin is live; restart again after each
change to pick it up. Run `claude plugin validate .` now and keep it
green after every change.

**2. Write the skill first** — have Claude interview it out of you:

> *"Interview me about integrating with [platform]. One question at a
> time. Chase edge cases, silent failures, and 'a 200 doesn't mean
> success' behavior. When we're done, draft `skills/<name>/SKILL.md`
> from my answers."*

Feed it your last few integration PR review threads and a postmortem if
you have one — it asks better questions. Domain experts are far better
at answering pointed questions than at enumerating what they know; half
of what's in our skill only surfaced because something asked. Then apply
three rules to the draft:

- The frontmatter `description` decides when Claude loads it. Make it
  pushy: list every phrase a user might say (*"the PIM"*, *"product
  sync"*), not just the product name.
- Keep SKILL.md under ~300 lines; push detail into `references/*.md`
  files it links to (Claude reads them on demand).
- Lead with your "rule zero" — the one mistake that causes the most damage.

Test the trigger: in a fresh session, ask something oblique (*"why is my
product sync dropping fields?"*) and confirm the skill loads.

**3. Add the agent** — a markdown file whose body is a workflow, not a
knowledge base. Ours is five verbs: DISCOVER, VERIFY, PLAN, BUILD, PROVE.
Have Claude draft it, then do the editing yourself: every API fact you
find in the prompt moves to the skill — the human's job here is cutting,
not writing. Omit the `tools:` frontmatter field unless you need to
restrict tools — **listing tools excludes MCP tools**. If users need a one-line
entry point, add a command: `commands/<name>.md` is just a prompt file
that hands off to the agent (that's all `/scaffold-connector` is).

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
is installed. This is the one place to make Claude work test-first: have
it write a dozen stdin/stdout test cases before the hook itself (see
`tests/` in this repo for a dependency-free pattern) — a hook bug means
either broken safety or blocked work.

**6. Ship it.** Push to a repo; teammates swap your local marketplace for
the real one:

```bash
claude plugin marketplace add your-org/my-plugin
claude plugin install my-plugin@<marketplace-name>
```
