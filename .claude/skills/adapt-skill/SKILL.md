---
name: adapt-skill
description: Adapt an imported skill file (SKILL.md) from another repo so it works correctly in this project. Fixes stale memory paths, wrong file references, wrong stack assumptions, and out-of-scope doc lists.
---

# Adapt Skill

When a `SKILL.md` is copied from another repo it carries the source repo's memory paths, file paths, directory conventions, and doc inventory. This skill audits and rewrites those references so the skill works in the current project without manual hunting.

## Steps

1. **Read the imported skill**
   Read the `SKILL.md` being adapted in full.

2. **Collect project facts** (run once, reuse across multiple skills in the same session)
   - Memory path: the project folder slug used in `~/.claude/projects/` — derive from the working directory (e.g. `c:/Users/andre/Downloads/F9_CongressTrading` → `c--Users-andre-Downloads-F9-CongressTrading`)
   - Root `.md` files: list files matching `*.md` at the repo root (excluding `.venv/`, `node_modules/`)
   - `.claude/` structure: list skills, agents, hooks present
   - Stack summary: check `CLAUDE.md` for the authoritative description of tech stack, entrypoints, ports, and conventions

3. **Audit the skill for stale references** — check each category:

   | Category | What to look for | How to fix |
   |----------|-----------------|------------|
   | Memory path | Any `c--Users-*` slug that isn't this project | Replace with the correct slug from step 2 |
   | Doc file paths | Paths like `docs/API.md`, `.claude/project-index.md`, or any file that doesn't exist here | Replace with the actual files in scope for this project |
   | Directory paths | `src/`, `server/`, `ml-service/` or other source dirs from the source repo | Replace with the directories that exist under this repo's root |
   | Stack references | Framework names, service names, or tooling from the source repo not present here | Replace or remove; consult `CLAUDE.md` for the authoritative stack |
   | Sister skill links | References to skills that don't exist in `.claude/skills/` | Update to skills that do exist, or remove the link |
   | Noise filters | Build artifact dirs (`build/`, `.next/`, etc.) in the "filter noise" step | Add this project's equivalents (`.venv/`, `node_modules/`, `frontend/dist/`) |
   | Decision rule examples | Concrete examples referencing source-repo patterns | Rewrite examples to match this project's naming conventions |

4. **Emit a verdict per category** before editing:
   - `Memory path: UPDATE — old slug X → new slug Y`
   - `Doc files: UPDATE — replaced docs/ table with AGENTS.md, PATTERNS_ROADMAP.md, MIGRATION_ROADMAP.md`
   - `Stack refs: SKIP — no foreign stack references found`
   - (etc.)

5. **Rewrite the skill** — apply only the changes identified. Do not restructure sections that are fine as-is. Preserve the skill's core logic, modes, and step numbering.

6. **Verify** — re-read the updated skill and confirm:
   - Every file path mentioned exists in the current repo (run a quick `Glob` or `Grep` if unsure)
   - The memory slug matches the current project directory exactly
   - No sister skill links point to skills that don't exist

## What never changes
- The skill's core purpose and step logic — only the project-specific references change.
- The frontmatter `name:` field (it must match the skill's directory name and the trigger in the harness).
- The `description:` field is updated only if the scope genuinely differs (e.g. the doc file list changed).
