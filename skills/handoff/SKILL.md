---
name: handoff
description: Writes the project handoff so it can be picked back up instantly. Updates the project's _Project-State/<Project>.md file (frontmatter + ## Resume Here block + pointers to docs/HTML/URLs). Use whenever you say "/handoff", "handoff", "write the handoff", "update project state", "log project", or at the end of any session where meaningful work happened on a named project. Also auto-run proactively at the end of sessions involving code, SaaS projects, or any named initiative even if not asked. Pairs with the /resume skill (handoff writes, resume reads).
---

# Handoff (Project State Writer)

Write the handoff for the project worked on this session so a future session (via the `/resume` skill) lands on the exact next action with zero searching. This is the WRITE side; `/resume` is the READ side. They share one home: `_Project-State/<Project>.md`.

## On invoke

First line of your response when this skill fires: print this banner exactly (rocket + label, inside one code block):

```
        /\
       /  \
      |    |
      |    |
      |    |
     /| |  |\
    / | |  | \
   /__|_|__|__\
      /_\/_\
       \||/
        \/
       (  )
      ( :: )
       (  )

   WRITING HANDOFF DOC
```

Then do the work below.

## Where project state lives

Project state files live in a `_Project-State/` folder. Point the skill at yours by setting the `CLAUDE_SKILLS_VAULT_PATH` environment variable (e.g. a notes vault or a docs repo). If it is unset, default to `$HOME/Documents/vault`, and the state file path is:

```
${CLAUDE_SKILLS_VAULT_PATH:-$HOME/Documents/vault}/_Project-State/<Project>.md
```

## What this skill does

Updates:
1. **Project state file** -> `_Project-State/<Project Name>.md` (the canonical handoff: frontmatter + `## Resume Here` block + pointers + body sections)
2. **Claude memory** (optional) -> if you keep a Claude Code memory file (`~/.claude/projects/<project>/memory/MEMORY.md`), add or update a one-line pointer to the state file. Skip this step if you do not use Claude memory.

## Step 1 - Identify the project

From the conversation, determine:
- Project name (e.g. "Project Alpha", "your side project")
- Status: `active`, `parked`, or `complete`
- Priority: 1 (highest) to 5 (lowest), judge from urgency and focus
- What was accomplished this session
- What's blocked or pending
- The single most important next physical action
- Pointers: any docs, HTML files, local paths, live URLs, dashboards, or notes worth jumping straight to

## Step 2 - Update the project state file

File: `${CLAUDE_SKILLS_VAULT_PATH:-$HOME/Documents/vault}/_Project-State/<Project Name>.md`

If it exists, read it first and preserve still-valid context. Then write this structure. The `## Resume Here` block goes at the very TOP of the body (this is what `/resume` reads):

```
---
type: project
status: [active|parked|complete]
priority: [1-5]
category: [work|personal|clients|...]
last_updated: [YYYY-MM-DD]
next_action: "[Single next physical action, verb+object format]"
goal: "[One sentence outcome]"
---

## Resume Here

**Where we stopped ([YYYY-MM-DD]):** [2-3 sentences on the current state]
**Next physical action:** [the one next action]
**Gotchas / don't-break:** [anything that would cause a mistake next session]
**Pointers:** [bullet list of docs / HTML files / local paths / live URLs / notes to jump to]

---

## Human To-Do (Order of Operations)

[A running checklist of tasks a HUMAN must do by hand - clicking through a tool, recording a video, making a call, etc. This is DISTINCT from the technical change/build log. It is the project's living to-do list. Maintain it every session: **DELETE completed items** (do not leave `[x]` clutter - a long list gets overwhelming; the completed work is preserved in the Change Log below). Add new items, keep the next action on top. Group by Active / Backlog / Go-live when the list grows. Skip this section only for pure-code projects where there are no human-side steps.]

- [ ] [next human action]
- [ ] [following human action]

---

## What's Working
[Bullet list of completed/functional features]

## What's Built
[Key files, components, integrations]

## Next Steps
[Numbered list of remaining work in priority order]

## Tech Stack / Key Details
[Relevant technical context, credential locations (not the secrets), table names, etc.]
```

Only include sections that are relevant. Don't pad. If your notes system uses wikilinks, keep them on every person/project/concept per your conventions.

## Step 3 - Update Claude memory (optional)

If you keep a Claude Code memory index (`~/.claude/projects/<project>/memory/MEMORY.md`), find the project's line (or add one). Update the one-line hook AND ensure it ends with a `STATE:` pointer so `/resume` finds the file instantly.

Format: `- [Project Name](project_slug.md) — current status in ~10 words. STATE: \`_Project-State/<Project Name>.md\``

Skip this step entirely if you do not use Claude memory.

## Guidelines

- **Be specific.** URLs, file paths, credential locations (not the secrets), table names - anything that saves time next session.
- **Next action must be physical.** "Wire up Stripe" is vague. "Add Stripe checkout API route to `/api/checkout/route.ts`" is actionable.
- **Don't lose context.** Preserve old decisions / tech-debt notes unless clearly outdated.
- **Status judgment:** `active` = worked on now. `parked` = waiting on external. `complete` = shipped.
- **Never write secrets.** Record where a credential lives, never the value.
- **Always confirm** after writing: one line saying what was updated and what `next_action` is set to.
