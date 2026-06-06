# PLAN-014: Add Project Update Skill

## Background and Goal

The latest Harness fixed assets can be updated in an already-onboarded target repository through the installer, but the semantic follow-up step is currently underspecified. `project-init` describes initial onboarding and can update the managed block through `init-project-entrypoint.py`, yet it does not clearly model the post-update workflow for synchronizing new Harness capabilities into the target agent entrypoint.

This plan adds a repo-local `project-update` skill that coordinates target project synchronization after fixed `.harness` assets have been updated. It preserves the existing deterministic boundaries: the installer copies fixed assets, `init-project-entrypoint.py` replaces only the managed block, and LLM review handles semantic conflicts outside the managed block.

## Scope

- Add `.harness/skills/project-update/SKILL.md`.
- Update `project-init` to distinguish first onboarding from update/synchronization.
- Document `project-update` in `.harness/ARCHITECTURE.md` and `installer/install-lifecycle.md`.
- Add regression tests for the new skill and updated lifecycle boundary.
- Add `project-update` to session startup core asset checks.
- Add the new skill and changed `.harness` assets to the installer payload and fixed asset manifest.

## Non-Scope

- Do not change `init-project-entrypoint.py` freeform parsing behavior.
- Do not let scripts infer semantic conflicts from arbitrary `AGENTS.md` prose.
- Do not update user-owned prose outside the managed block automatically.
- Do not change `project-env-contract` behavior or overwrite project environment contracts.
- Do not create a separate installer runtime gate.

## Implementation Direction

Treat `project-update` as a semantic coordination skill for already-onboarded repositories. Its expected sequence is: run the deterministic installer update first, verify fixed assets are present, inspect existing entrypoints and project-entrypoints contract, replace only the Harness managed block through `init-project-entrypoint.py --write`, report conflicts or marker-outside recommendations for user-owned prose, and delegate environment contract refresh only when new project evidence requires it.

## File Boundaries

- Create: `.harness/skills/project-update/SKILL.md`
- Create: `.harness/tests/test_project_update_skill.py`
- Create: `src/harness_engineering_installer/payload/.harness/skills/project-update/SKILL.md`
- Modify: `.harness/skills/project-init/SKILL.md`
- Modify: `.harness/ARCHITECTURE.md`
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/tests/test_project_init_skill.py`
- Modify: `.harness/tests/test_session_start.py`
- Modify: `installer/install-lifecycle.md`
- Modify: `installer/tests/test_install_lifecycle.py`
- Modify: `src/harness_engineering_installer/assets-manifest.json`
- Modify: `src/harness_engineering_installer/payload/.harness/ARCHITECTURE.md`
- Modify: `src/harness_engineering_installer/payload/.harness/skills/project-init/SKILL.md`
- Modify: `src/harness_engineering_installer/payload/.harness/scripts/session-start.py`
- Modify: `src/harness_engineering_installer/payload/.harness/tests/test_project_init_skill.py`
- Modify: `src/harness_engineering_installer/payload/.harness/tests/test_session_start.py`
- Test: `.harness/tests/test_project_update_skill.py`
- Test: `.harness/tests/test_project_init_skill.py`
- Test: `.harness/tests/test_session_start.py`
- Test: `installer/tests/test_install_lifecycle.py`
- Test: `installer/tests/test_asset_manifest.py`
- Test: `installer/tests/test_installer_engine.py`

## Task Decomposition

This is one L2 task because source `.harness` assets and installer payload assets must remain synchronized in the same completion boundary. Splitting the work would leave a temporary state where installer fixed assets no longer match the source framework.

## Verification Strategy

Run targeted skill, lifecycle, startup, and installer asset tests. Also run Harness state/lint checks and the language standardization guard to ensure the new skill remains English and fixed-asset compatible.

## Architecture Impact

- Expected target project architecture impact: root `ARCHITECTURE.md` remains unchanged; this work changes Harness framework behavior only.
- Expected Harness framework architecture impact: `.harness/ARCHITECTURE.md`, `.harness/skills/`, session startup core asset checks, installer lifecycle docs, manifest, payload, and tests are expected to change to include `project-update`.
- This is a workflow gate record, not a standalone task.

## Risks and Open Questions

- Risk: Naming the skill too broadly as `update` could blur installer asset copying with semantic entrypoint synchronization. The skill must be named `project-update` and explicitly keep installer update separate.
- Risk: The skill could accidentally authorize rewriting user-owned prose outside the managed block. The instructions and tests must block that.
- Open questions: None blocking. The user approved adding a post-update skill after the analysis.

## Plan Review Gate

Status: passed
Reviewer: harness-reviewer
Reviewed At: 2026-06-06T20:57:39+08:00

Checks:
- Scope, non-scope, file boundaries, acceptance, and verification are reviewable.
- The task is a delivery unit, not a testing or review task.
- Architecture Impact is recorded as a gate, not a standalone task.
- Source `.harness` assets and installer payload assets remain in one task boundary.
- The plan does not require direct writes to `workflow-state.json` or hand-authored `tasks.json`.

Findings:
- No blocking findings.

## Task Contracts

<a id="task-001-add-project-update-skill"></a>

### TASK-001: Add project-update skill

Goal: Add a repo-local `project-update` skill for synchronizing already-onboarded target projects after Harness fixed asset updates.

Files:
- Create: `.harness/skills/project-update/SKILL.md`
- Create: `.harness/tests/test_project_update_skill.py`
- Create: `src/harness_engineering_installer/payload/.harness/skills/project-update/SKILL.md`
- Modify: `.harness/skills/project-init/SKILL.md`
- Modify: `.harness/ARCHITECTURE.md`
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/tests/test_project_init_skill.py`
- Modify: `.harness/tests/test_session_start.py`
- Modify: `installer/install-lifecycle.md`
- Modify: `installer/tests/test_install_lifecycle.py`
- Modify: `src/harness_engineering_installer/assets-manifest.json`
- Modify: `src/harness_engineering_installer/payload/.harness/ARCHITECTURE.md`
- Modify: `src/harness_engineering_installer/payload/.harness/skills/project-init/SKILL.md`
- Modify: `src/harness_engineering_installer/payload/.harness/scripts/session-start.py`
- Modify: `src/harness_engineering_installer/payload/.harness/tests/test_project_init_skill.py`
- Modify: `src/harness_engineering_installer/payload/.harness/tests/test_session_start.py`
- Test: `.harness/tests/test_project_update_skill.py`
- Test: `.harness/tests/test_project_init_skill.py`
- Test: `.harness/tests/test_session_start.py`
- Test: `installer/tests/test_install_lifecycle.py`
- Test: `installer/tests/test_asset_manifest.py`
- Test: `installer/tests/test_installer_engine.py`

Depends on: []

Acceptance:
- `.harness/skills/project-update/SKILL.md` exists with concise frontmatter and describes post-installer-update synchronization for already-onboarded repositories.
- `project-update` requires fixed assets to be updated by the installer before semantic entrypoint synchronization.
- `project-update` replaces only the Harness managed block through `init-project-entrypoint.py --write` and does not rewrite user-owned prose outside the managed block.
- `project-update` reports semantic conflicts and marker-outside recommendations instead of letting deterministic scripts infer them.
- `project-init` points already-onboarded update work to `project-update` while preserving first-onboarding behavior.
- Session startup core asset checks include `.harness/skills/project-update/SKILL.md`.
- Installer lifecycle, source `.harness` assets, payload assets, and manifest all include the new skill.

Verification:
- Run: `python3 .harness/tests/test_project_update_skill.py`
- Run: `python3 .harness/tests/test_project_init_skill.py`
- Run: `python3 .harness/tests/test_session_start.py`
- Run: `python3 installer/tests/test_install_lifecycle.py`
- Run: `python3 installer/tests/test_asset_manifest.py`
- Run: `python3 installer/tests/test_installer_engine.py`
- Run: `python3 .harness/tests/test_language_standardization.py`
- Check: `cmp -s .harness/skills/project-update/SKILL.md src/harness_engineering_installer/payload/.harness/skills/project-update/SKILL.md`
