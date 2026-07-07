#!/usr/bin/env bash
set -euo pipefail

# Installs a curated set of Claude Code skills into ~/.claude/skills/
# Usage: curl -sSL https://raw.githubusercontent.com/Icarus-312/claude-skills/main/install.sh | bash

REPO="Icarus-312/claude-skills"
BRANCH="main"
SKILLS_DIR="${HOME}/.claude/skills"
TARBALL_URL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"

echo "Installing Claude Code skills from ${REPO}..."

mkdir -p "${SKILLS_DIR}"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

# Fetch and extract the repo tarball
curl -sSL "${TARBALL_URL}" | tar -xz -C "${TMPDIR}"

# The extracted top-level dir is <repo>-<branch>
SRC_ROOT="$(find "${TMPDIR}" -maxdepth 1 -type d -name 'claude-skills-*' | head -n1)"
SRC_SKILLS="${SRC_ROOT}/skills"

if [ ! -d "${SRC_SKILLS}" ]; then
  echo "Error: could not find skills/ in the downloaded repo." >&2
  exit 1
fi

for skill_path in "${SRC_SKILLS}"/*/; do
  name="$(basename "${skill_path}")"
  dest="${SKILLS_DIR}/${name}"

  if [ -e "${dest}" ]; then
    # Probe whether a real terminal is actually usable (curl|bash has no stdin tty).
    if { exec 3<>/dev/tty; } 2>/dev/null; then
      printf "Skill '%s' already exists. [o]verwrite / [s]kip / [b]ackup? " "${name}" >&3
      read -r choice <&3
      exec 3>&-
    else
      # No terminal attached: back up instead of clobbering.
      choice="b"
      echo "Skill '${name}' already exists; no terminal for a prompt — backing up."
    fi
    case "${choice}" in
      o|O)
        rm -rf "${dest}"
        ;;
      b|B)
        mv "${dest}" "${dest}.bak.$$"
        echo "  backed up existing to ${dest}.bak.$$"
        ;;
      *)
        echo "  skipped ${name}"
        continue
        ;;
    esac
  fi

  cp -R "${skill_path%/}" "${dest}"
  echo "✓ installed ${name}"
done

echo "Done. Restart Claude Code or run /help to see new skills."
