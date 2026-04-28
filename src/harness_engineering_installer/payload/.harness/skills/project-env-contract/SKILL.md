---
name: project-env-contract
description: Use when deriving project-specific environment contracts for a target development repository.
---

# Project Environment Contract

## Overview

Initialize the project environment contract for a real project by deriving project-specific checks from repository evidence. This skill creates the semantic bridge between generic Harness assets and the target repository's build, test, runtime, and operational expectations.

The primary output is `.harness/contracts/project-contracts.json`, validated by `.harness/schemas/project-contracts.schema.json`. `project-contracts.json may be absent until project-env-contract configures it`; in that state, `check-project-env.py` reports `NOT_CONFIGURED` instead of treating the Harness core as broken. Contracts are the truth source; `.harness/scripts/check-project-env.py` only executes declared checks. Do not turn project-specific environment knowledge into ad hoc `session-start.py` checks.

## Repository Evidence First

Read repository evidence before asking user questions.

Use the target repository to identify:

- entry instructions such as `AGENTS.md`, `README.md`, or local architecture notes;
- package manifests, lockfiles, build files, CI definitions, and test runners;
- existing scripts for lint, build, test, code generation, migration, and local services;
- language, framework, platform, database, service, emulator, simulator, and secret requirements;
- current Harness assets, active `work/` state, and any existing project contracts.

Do not ask the user to restate information that is discoverable from repository files. If evidence conflicts, name the files and state the conflict before proposing a contract.

## Blocking Questions

Ask only questions that block a verifiable contract.

A blocking question must name:

- the missing decision;
- the contract field or check it affects;
- the risk of choosing without confirmation;
- the proposed default if one is safe.

Do not ask broad preference questions before reading evidence. If uncertainty is non-blocking, record it as a warning or follow-up rather than stopping initialization.

## Core Checks vs Project Checks

Harness core checks protect the Harness system itself: schemas, templates, rules, scripts, required repo-local skills, active plan shape, workflow state shape, and lifecycle invariants.

Project environment checks protect the target project: toolchain versions, dependency installation, build commands, test commands, local services, credentials, device targets, generated files, and deploy or packaging prerequisites.

Keep this boundary explicit:

- Do not add project-specific checks to `session-start.py`.
- Do not put project runtime facts into Harness core schemas unless they are generic Harness contract fields.
- Do not write `workflow-state.json` directly.
- Use `state-write.py` for workflow state and `update-task.py` for task execution state.

## Required Project Contracts

Prefer declarative contracts that deterministic scripts can validate later. A complete initialization should write or revise `.harness/contracts/project-contracts.json` with these concepts before any custom checker exists:

- project profile: project type, language, framework, package manager, runtime targets, and source roots;
- environment checks: required tools, versions, services, secrets, ports, device targets, generated assets, and network assumptions;
- command registry: canonical commands for install, lint, build, unit test, integration test, smoke test, code generation, migration, and cleanup;
- severity model: each check is either blocking or warning, with clear remediation guidance;
- evidence source: every inferred contract links back to repository files or an explicit user answer.

Each environment check should have a stable id, description, evidence source, command reference or deterministic probe, expected result, severity, and remediation. Use `python3 .harness/scripts/check-project-env.py --root . --contract .harness/contracts/project-contracts.json` to execute the declared checks after the contract exists.

## Contracts Before Scripts

Write project contracts before custom scripts or adapters.

Only introduce a custom checker when a contract is already stated and cannot be validated with an existing generic script or command registry entry. When that happens, describe the adapter fallback explicitly:

- which contract field cannot be checked declaratively;
- why an adapter is necessary;
- what input and output shape the adapter must use;
- how failures map to blocking or warning severity.

Adapters must consume contracts. They must not invent requirements that are absent from the project profile, environment checks, or command registry. `check-project-env` may call adapters only as a fallback for contract-declared checks; adapters are never the truth source.

## Output Boundary

This skill may guide the Agent to create or revise `.harness/contracts/project-contracts.json`. `project-contracts.json may be absent until project-env-contract configures it`; that missing-file state is `NOT_CONFIGURED`, not a reason to add project-specific checks to `session-start.py`. If a target repository needs a different contract location, propose it explicitly and explain why it belongs outside `session-start.py`.

This skill must not:

- activate tasks;
- change workflow phase;
- write `workflow-state.json` directly;
- mark tasks as tested, reviewed, or done;
- add project-specific environment checks to `session-start.py`;
- replace deterministic validation scripts with LLM judgment.

## Validation

Before claiming initialization is ready, verify:

- repository evidence was reviewed before user questions;
- project profile, environment checks, command registry, severity, and remediation are represented;
- blocking and warning severities are distinguishable;
- adapter fallback is documented only after contracts exist;
- Harness core checks remain separate from project environment checks;
- `session-start.py` still validates Harness startup only.
