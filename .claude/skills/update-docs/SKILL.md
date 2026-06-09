---
name: update-docs
description: Update the long-form documentation files (AGENTS.md, PATTERNS_ROADMAP.md, MIGRATION_ROADMAP.md) so they reflect what actually shipped. Has per-file decision rules and never edits a doc whose scope didn't change.
---

# Update Docs

Keep the long-form documentation files in sync with the codebase. Each file has a narrow scope — only touch a file when a change actually crosses into that scope. Sister skills cover other doc surfaces:

- [sync-claude-context](../sync-claude-context/SKILL.md) — root-level `README.md`, `CLAUDE.md`, `PROJECT_INDEX.md`

---

## Files in scope

| File | Scope |
|------|-------|
| [AGENTS.md](../../../AGENTS.md) | Module reference, CLI commands, data model, API architecture, conventions. Authoritative for the Python data layer. |
| [PATTERNS_ROADMAP.md](../../../PATTERNS_ROADMAP.md) | Planned pattern-detection features; entries graduate out when shipped |
| [MIGRATION_ROADMAP.md](../../../MIGRATION_ROADMAP.md) | Migration plan for ongoing architectural transitions (e.g. Streamlit → FastAPI+React) |

---

## Modes

### A — Session sync (default)
Used right after finishing a task. Base the audit on the files created/modified/deleted in the current conversation.

### B — Git history audit
Used standalone or when docs have drifted. Run:
```
git log --oneline -30
```
Inspect each non-noise commit with `git show --stat <sha>` and apply the per-file rules below.

Both modes can be combined — git first, then layer in uncommitted session work.

---

## When to run
- After a new CLI command, Python module, API router, or data model change ships
- After a new pattern-detection feature ships (or is explicitly planned)
- After a migration phase completes or its strategy changes
- Periodically to catch drift (10+ commits since last update)

Do NOT run for: in-progress feature branches, experimental spikes, unmerged work.

---

## Decision rules per file

### `AGENTS.md`
UPDATE when:
- A new CLI command is added or removed (`python -m src.main <command>`)
- A new Python module is added under `src/` with a distinct purpose
- The data model changes (new SQLite table, new column, new schema)
- The API architecture changes (new router, new repository method, new analytics module)
- A new environment variable is introduced or an existing one changes meaning
- A convention changes (e.g. new naming pattern for analytics files)

SKIP for: internal refactors that don't change the public interface, bug fixes that restore documented behaviour, test-only changes.

### `PATTERNS_ROADMAP.md`
UPDATE when:
- A planned pattern-detection feature ships → REMOVE the bullet (note it shipped)
- A new planned pattern item is explicitly added by the user
- A planned item is explicitly dropped or deprioritised by the user
- The implementation approach for a planned item changes materially

Do NOT add speculative items the user has not asked for. Roadmap is not a brainstorm.

### `MIGRATION_ROADMAP.md`
UPDATE when:
- A migration phase completes → mark it done / remove it from the pending list
- The migration strategy or phasing changes (e.g. scope of a phase expands or shrinks)
- A new migration concern is identified that affects the plan
- A phase's success criteria or acceptance test changes

SKIP for: incremental work within an already-documented phase that doesn't change the plan.

---

## Steps

1. **Collect changes**
   - *Session mode:* list every file created, modified, or deleted in this conversation.
   - *Git mode:* `git log --oneline -30`; for each non-noise commit, `git show --stat <sha>`.

2. **Filter noise** — drop `*.test.*`, `*.spec.*`, `build/`, `node_modules/`, `.venv/`, formatting-only diffs, and reverts of already-audited commits.

3. **Evaluate each file** — apply the rules above. Emit a one-line verdict per file:
   - `AGENTS.md: UPDATE — reason` or `AGENTS.md: SKIP — reason`
   - `PATTERNS_ROADMAP.md: UPDATE — reason` or `PATTERNS_ROADMAP.md: SKIP — reason`
   - `MIGRATION_ROADMAP.md: UPDATE — reason` or `MIGRATION_ROADMAP.md: SKIP — reason`

4. **Read before editing** — for every file marked UPDATE, read the current contents first. Never overwrite content that is still accurate. For `AGENTS.md` (the longest doc), use offset/limit to read only the sections you'll touch.

5. **Apply minimal edits** — add or update only the affected sections. Match the existing voice (declarative, present-tense). Backtick file paths, env vars, CLI commands, table names. Keep table-row style consistent inside `AGENTS.md`.

6. **Cross-doc consistency** — if you updated an env var name, CLI command, or module path in one doc, grep the other docs for the old token and update them too. Stale cross-references are the most common drift.

7. **Verify**
   - Re-read each updated section.
   - Confirm every artifact mentioned (file path, env var, CLI command, table name) actually exists in the current tree. Run a quick `Grep` if unsure.
   - For `PATTERNS_ROADMAP.md` or `MIGRATION_ROADMAP.md` removals, confirm the item is accurately reflected elsewhere if needed.

8. **Do NOT**
   - Do NOT commit. The user commits explicitly.
   - Do NOT update `README.md`, `CLAUDE.md`, or `PROJECT_INDEX.md` from this skill — use [sync-claude-context](../sync-claude-context/SKILL.md).
   - Do NOT add speculative or "planned" content (except in roadmap files, and only at the user's request).
   - Do NOT reformat or reorganise sections that didn't change.
   - Do NOT add emojis.

---

## What never changes
- The English-only rule across all docs.
- The structural skeleton of each file (existing heading hierarchy, table column order in `AGENTS.md`).
- The separation of concerns between these files and the root-level docs handled by [sync-claude-context](../sync-claude-context/SKILL.md).
