---
name: resume
description: Pick a project back up fast with zero searching. Use whenever you say "resume [project]", "pick this back up", "where did we leave off on [project]", "continue [project]", "/resume", or otherwise point at a named project and want to keep going. Runs a fixed lookup order so there is no grep / fan-out.
---

# Resume a Project

Goal: get back into a project in seconds, landing on the exact next physical action. No searching, no guessing locations. Follow this order exactly and stop as soon as you have the next action.

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

   RESUMING PROJECT
```

Then run the lookup below.

## Where project state lives

Project state files live in a `_Project-State/` folder inside the path set by the `CLAUDE_SKILLS_VAULT_PATH` environment variable. If unset, default to `$HOME/Documents/vault`:

```
${CLAUDE_SKILLS_VAULT_PATH:-$HOME/Documents/vault}/_Project-State/<Project>.md
```

## Lookup order (deterministic)

1. **Claude memory (optional shortcut)** — if you keep a Claude Code memory index (`~/.claude/projects/<project>/memory/MEMORY.md`), read it and find the line matching the named project. That line carries a `STATE:` path pointing at the canonical state file. If you do not use Claude memory, skip straight to step 2.

2. **Canonical state file** — open `_Project-State/<Project>.md` (list the most recently-updated files in that folder and ask which one if no project was named). Read:
   - the `## Resume Here` block (where we stopped, next physical action, gotchas), and
   - the `next_action` + `last_updated` frontmatter fields.
   This is the single source of truth. It IS the handoff doc.

3. **Recent notes (only if stale)** — if `last_updated` is more than ~5 days old, or the `## Resume Here` block is missing/thin, check the most recent daily/work notes for anything newer. Otherwise skip this step.

Stop here. Two or three reads max in the common case.

## Output

Lead with the next physical action, then one tight status line, then any don't-break gotchas. Format:

```
Resuming **<Project>** (last touched <date>).

**Next action:** <the next_action / Resume Here action>
**Status:** <one line>
**Don't break:** <gotchas, if any>
**Human to-do:** <the next 2-3 unchecked items from the `## Human To-Do (Order of Operations)` block, if the file has one>
```

If the state file has a `## Human To-Do (Order of Operations)` block, read it and surface the next few open items - this is the human-side checklist (clicks, calls, recordings) separate from the technical log. Skip the line if the file has no such block.

Then ask whether to start on the next action or review the full state file.

## If there is no state file

If the named project has no `_Project-State/<Project>.md`, say so and offer to create one (it should have `type: project` frontmatter and a `## Resume Here` block at top). Then fold whatever context exists into it so next time `/resume` lands clean.

## Maintenance rule (enforce every session end on a project)

Handoff content lives ONLY in `_Project-State/<Project>.md`. When wrapping a project work session, update that file's `## Resume Here` block + `next_action` + `last_updated`. The `/handoff` skill does this heavier write (handoff writes, resume reads).
