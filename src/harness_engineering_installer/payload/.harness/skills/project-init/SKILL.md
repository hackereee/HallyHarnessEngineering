---
name: project-init
description: Use when initializing Harness in a real project by detecting agent entrypoints, installing Harness architecture references, and delegating environment contracts.
---

# Project Init

## Overview

Initialize Harness in a real project after the fixed `.harness/` assets have been installed. This top-level skill connects the target repository's agent entrypoint to the stable Harness framework architecture and then delegates project environment contract derivation to `project-env-contract`.

This skill is about onboarding and coordination. It must not replace deterministic scripts, write workflow runtime state directly, or turn project-specific environment checks into Harness core startup checks.

## Installed Harness Assets Precondition

Project initialization assumes the fixed `.harness/` assets have already been released into the target repository by a deterministic installer. That installer owns framework asset copying, version checks, and preservation of target runtime data such as `work/` and `.harness/contracts/`. Installer lifecycle design belongs outside the runtime `.harness/` framework.

Before entrypoint integration, verify that core assets such as `.harness/ARCHITECTURE.md`, `.harness/rules/`, `.harness/schemas/`, `.harness/templates/`, `.harness/scripts/`, and `.harness/skills/` exist. If they are missing, report `HARNESS_ASSETS_MISSING` and run or request the installer first. Do not reconstruct partial Harness assets from memory and do not paste Harness framework prose into target project files.

## Entrypoint Detection

Inspect repository evidence before writing references. Detect agent entrypoint candidates in this order:

1. Canonical generic entrypoint:
   - `AGENTS.md`
2. Tool-specific entrypoints:
   - `CLAUDE.md`
   - `GEMINI.md`
   - `.github/copilot-instructions.md`
3. Editor or agent rule files:
   - `.cursor/rules/*.mdc`
   - `.cursorrules`
   - `.windsurfrules`
   - `.windsurf/rules/*.md`
   - `.clinerules`
   - `.roo/rules/*.md`

If `AGENTS.md` exists, use it as the canonical entrypoint. If multiple tool-specific entrypoints exist without `AGENTS.md`, report the candidates and recommend creating `AGENTS.md` as the canonical entrypoint unless the user explicitly chooses another entrypoint.

If no agent entrypoint exists, report `NEEDS_ENTRYPOINT` and recommend creating `AGENTS.md` unless the user explicitly chooses another entrypoint. Do not silently write to `README.md`, `CONTRIBUTING.md`, or root `ARCHITECTURE.md`; those are human-facing fallback evidence, not agent entrypoints by default.

## Workflow Integration Review

Before writing or recommending entrypoint changes, read all detected entrypoints before workflow conclusions. This includes the canonical entrypoint and any tool-specific or editor rule files found during Entrypoint Detection. Do not assume that `AGENTS.md` is the only workflow source when `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.cursor/rules/*.mdc`, `.cursorrules`, `.windsurfrules`, `.windsurf/rules/*.md`, `.clinerules`, or `.roo/rules/*.md` also exist.

Map target project workflow instructions onto Harness lifecycle semantics instead of creating a second state machine:

- startup and resume rules map to `session-start.py`;
- planning maps to `planning`;
- development maps to `implementing`;
- tests map to the `testing` gate;
- reviews map to the `reviewing` gate;
- task completion commits map to `commit-task.py`;
- L0/L1 completion maps to `complete-workflow.py`;
- L2/L3 archive maps to `archive-plan.py`;
- incoming work maps to `backlog-intake.py`.

Conflicts must be surfaced, not silently normalized. If target entrypoints define workflow, task, testing, review, state, commit, handoff, backlog, or archive rules that conflict with Harness lifecycle, report conflicts before modifying user-owned prose. Compatible project rules remain valid; conflicting workflow semantics must be mapped to Harness phases, gates, truth sources, and write gateways.

The semantic conflict judgment belongs to the LLM, not `init-project-entrypoint.py`. Do not parse freeform entrypoint prose in deterministic scripts to decide whether workflow rules conflict. Deterministic scripts may manage block markers, block versions, canonical entrypoint metadata, architecture references, and contract shape; they must not infer intent from arbitrary human prose.

During review, keep these write gateways explicit:

- `workflow-state.json` is written through `state-write.py` or lifecycle tools that call it;
- `tasks.json` is initialized through `materialize-tasks.py` and updated through `update-task.py`;
- phase transitions should use `lifecycle-transaction.py` when available;
- backlog writes use `backlog-intake.py`;
- project environment commands and checks stay delegated to `project-env-contract`.

## Architecture Reference

Harness framework architecture belongs at `.harness/ARCHITECTURE.md`.

The target repository's root `ARCHITECTURE.md` remains business architecture. The project init flow must ensure root `ARCHITECTURE.md` exists; if it is missing, create an empty root `ARCHITECTURE.md` so future task completion summaries can judge whether project architecture should be updated. Do not paste the Harness framework architecture into root `ARCHITECTURE.md`. The entrypoint should reference both documents with separate meanings:

- root `ARCHITECTURE.md`: business architecture, modules, runtime topology, and project boundaries;
- `.harness/ARCHITECTURE.md`: Harness framework architecture, lifecycle, schemas, scripts, rules, skills, and `work/` runtime layout.

If `.harness/ARCHITECTURE.md` is missing, stop with `HARNESS_ASSETS_MISSING` and run the fixed-asset installer before inserting entrypoint references.

## Managed Block Update

Entrypoint changes must go through a deterministic managed block, not freeform rewriting. The block markers are:

```md
<!-- harness-engineering:start -->
<!-- harness-engineering:end -->
```

The managed block must tell future agents to read:

1. the current agent entrypoint;
2. root `ARCHITECTURE.md`;
3. `.harness/ARCHITECTURE.md`;
4. `.harness/rules/workflow-lifecycle.md`;
5. scenario rules such as `.harness/rules/session-start.md`, `.harness/rules/handoff-rules.md`, `.harness/rules/archive-rules.md`, and `.harness/rules/backlog-rules.md`;
6. `.harness/contracts/`.

It must also name the truth sources:

- workflow runtime: `work/workflow-state.json`;
- task runtime: `work/plans/active/<PLAN-ID>/tasks.json`;
- planning contract: `work/plans/active/<PLAN-ID>/plan.md`;
- recovery summary: `work/plans/active/<PLAN-ID>/handoff.md`;
- project environment contract: `.harness/contracts/project-contracts.json`;
- project entrypoint contract: `.harness/contracts/project-entrypoints.json`.

Do not modify content outside the managed block. If a managed block already exists, replace that block only.

## Entrypoint Integration Boundary

Entrypoint integration is not a full-text merge of `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, Copilot instructions, or editor rule files.

All detected entrypoints are read for semantic review, but only the canonical entrypoint receives the Harness managed block by default; tool-specific entrypoints are read for semantic review and conflict detection, but they are not auto-merged, not rewritten to mirror `AGENTS.md`, and not patched unless the user explicitly chooses that entrypoint as canonical or asks for a separate edit.

The Agent may recommend marker outside changes when target prose conflicts with Harness lifecycle, but those changes are user-owned prose edits and must be handled separately from the deterministic managed block update.

## Environment Contract Delegation

After the entrypoint and Harness architecture reference are configured, delegate project environment contract derivation to `project-env-contract`.

The delegated output is `.harness/contracts/project-contracts.json`. This skill may verify that the file exists or report that it remains `NOT_CONFIGURED`, but it must not duplicate the `project-env-contract` rules such as project profile extraction, command registry construction, environment check severity mapping, or adapter fallback policy.

## Output Boundary

This skill may guide the Agent to:

- choose or create an agent entrypoint;
- create an empty root `ARCHITECTURE.md` when the real project does not have one;
- verify installed Harness framework assets are present;
- run the deterministic entrypoint updater;
- create or update `.harness/contracts/project-entrypoints.json`;
- invoke `project-env-contract` for `.harness/contracts/project-contracts.json`.

This skill must not:

- write `workflow-state.json` directly;
- write `tasks.json` directly;
- activate tasks or change workflow phase;
- add project-specific checks to `session-start.py`;
- rewrite root `ARCHITECTURE.md` with Harness framework architecture;
- mutate user entrypoint prose outside the managed block;
- auto-merge tool-specific entrypoints into the canonical entrypoint or vice versa.

## Validation

Before claiming initialization is ready, verify:

- an agent entrypoint exists or the user explicitly chose to create one;
- root `ARCHITECTURE.md` exists, even if it is initially empty;
- the managed block is present exactly once in the canonical entrypoint;
- `.harness/ARCHITECTURE.md` exists and is referenced by the entrypoint;
- `.harness/contracts/project-entrypoints.json` records the canonical entrypoint;
- `project-env-contract` has either produced `.harness/contracts/project-contracts.json` or intentionally remains `NOT_CONFIGURED`;
- Harness core checks remain separate from project environment checks.
