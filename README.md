# claude-skills

A small, forkable set of Claude Code skills for managing project state — write a handoff at the end of a session, resume exactly where you left off next time.

## Quick install

```bash
curl -sSL https://raw.githubusercontent.com/Icarus-312/claude-skills/main/install.sh | bash
```

Installs each skill into `~/.claude/skills/`. If a skill already exists it asks: overwrite / skip / backup.

## Manual install

```bash
git clone https://github.com/Icarus-312/claude-skills.git
cp -R claude-skills/skills/* ~/.claude/skills/
```

Then restart Claude Code (or run `/help`).

## What's inside

- **handoff** — writes/updates a project's `_Project-State/<Project>.md` file (frontmatter + `## Resume Here` block + pointers) so the work can be picked back up instantly.
- **resume** — reads that state file in a fixed lookup order and drops you straight onto the next physical action, no searching.

They pair: `handoff` writes, `resume` reads. Both use a shared `_Project-State/` folder.

## Configure where state lives

Both skills read/write a `_Project-State/` folder. Point them at yours with an environment variable (a notes vault, a docs repo, anywhere):

```bash
export CLAUDE_SKILLS_VAULT_PATH="$HOME/Documents/vault"
```

If unset, it defaults to `$HOME/Documents/vault`.

## How to use

End of a work session:

```
/handoff
```
→ writes `_Project-State/Project Alpha.md` with the next action and current state.

Next session:

```
/resume Project Alpha
```
→ reads the state file and leads with the exact next physical action.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- macOS or Linux

## Uninstall

```bash
rm -rf ~/.claude/skills/handoff
rm -rf ~/.claude/skills/resume
```
