---
name: project-update
description: Use when synchronizing an already-onboarded target project after Harness fixed assets have been updated.
---

# Project Update

## Overview

Synchronize an already-onboarded target project after the deterministic installer has updated fixed `.harness/` assets. This skill coordinates semantic entrypoint review and managed block synchronization; it does not copy framework assets.

Use `project-init` for first onboarding. Use `project-update` only when the target project already has Harness assets, an agent entrypoint, or `.harness/contracts/project-entrypoints.json`.

## Preconditions

Fixed `.harness/` assets must already be present and current in the target project.

- Run or request `hally-harness-engineering update <target>` before semantic synchronization.
- Verify core assets such as `.harness/ARCHITECTURE.md`, `.harness/templates/entrypoint-managed-block.template.md`, `.harness/scripts/init-project-entrypoint.py`, and `.harness/skills/project-update/SKILL.md`.
- If fixed assets are missing, report `HARNESS_ASSETS_MISSING`.
- Do not copy fixed assets manually, reconstruct partial assets from memory, or paste Harness framework prose into target project files.

## Entrypoint Synchronization

Read the canonical entrypoint and detected tool/editor entrypoints before making workflow conclusions. Use the same entrypoint candidates as `project-init`: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, Copilot instructions, and editor rule files.

Managed block synchronization is deterministic:

- Run `.harness/scripts/init-project-entrypoint.py --write --entry <canonical-entrypoint>` or the equivalent `harness init-entrypoint` command.
- The script may replace only the Harness managed block.
- Do not rewrite user-owned prose outside the managed block.
- If prose outside the block conflicts with Harness lifecycle, report a marker-outside recommendation instead of editing it automatically.

## Semantic Review Boundary

The semantic conflict judgment belongs to the Agent; deterministic scripts must not infer intent from arbitrary entrypoint prose.

Review whether target project instructions conflict with Harness startup, planning, task execution, testing, review, commit, handoff, backlog, or archive semantics. The Agent must report conflicts before changing user-owned prose. Compatible project-specific rules remain valid.

## Contract and Runtime Boundaries

- Do not write `workflow-state.json`.
- Do not write `tasks.json`.
- Do not activate tasks, consume backlog, complete workflows, or archive plans.
- Entry point managed block updates must not overwrite `.harness/contracts/project-contracts.json`.
- Refresh `.harness/contracts/project-entrypoints.json` only through `init-project-entrypoint.py`.
- When project environment facts changed, delegate to `project-env-contract`; do not edit or replace that contract from this skill.

## Validation

Before claiming synchronization is ready, verify:

- Fixed Harness assets are present after installer update.
- The canonical entrypoint has exactly one Harness managed block.
- The managed block version matches `.harness/templates/entrypoint-managed-block.template.md`.
- `.harness/contracts/project-entrypoints.json` records the canonical entrypoint and current managed block version.
- Any user-owned prose conflicts are reported as recommendations, not silently normalized.
- Runtime state and task state were not modified.
