# PLAN-003: Add Project Init Skill

## Background and Goal

Add a repo-local skill that helps initialize Harness in a real development repository by producing project-specific environment contracts. The skill must keep Harness core checks separate from project checks: `session-start.py` continues to validate Harness itself, while the initialization skill guides the Agent to derive project profile and environment check contracts from the target repository and user-provided constraints.

## Scope

- Add a repo-local skill for project initialization.
- Require the new skill as a Harness asset during session startup.
- Add deterministic tests for the new asset gate and skill contract content.
- Document the skill in the Harness architecture overview.

## Non-Scope

- Do not implement `.harness/contracts/` schemas in this plan.
- Do not implement `check-env.py` in this plan.
- Do not add project-specific environment checks to `session-start.py`.
- Do not change workflow lifecycle state semantics.

## Implementation Direction

Treat the new skill as a semantic initializer, not a runtime checker. The skill should instruct Agents to inspect repository evidence, ask only blocking questions, generate project environment/profile contracts for later deterministic checks, and avoid writing `workflow-state.json` or project-specific checks into `session-start.py`.

## File Boundaries

- Create: `.harness/skills/project-init/SKILL.md`
- Create: `.harness/tests/test_project_init_skill.py`
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/tests/test_session_start.py`
- Modify: `harness-design/architecture.md`

## Task Decomposition

The plan starts by creating the project-init skill and its content-level contract test. The second task gates the new skill as a required Harness asset after the asset exists, so lifecycle preflight cannot block the workflow between tasks. The final task documents the skill in the architecture overview and validates the full touched surface.

## Verification Strategy

Run the project-init skill test before and after creating the skill. Run the targeted session-start test before and after updating required assets. Finish with session-start, project-init, and lint validations.

## Risks and Open Questions

- Risk: The skill may be written too broadly and imply project checks belong in `session-start.py`; the skill and architecture text must explicitly preserve the core/project boundary.
- Risk: The skill may ask the Agent to generate arbitrary scripts before contracts; the skill must prefer contracts first and adapters only when declared checks cannot express the requirement.
- Open questions: None for this initial repo-local skill.

## Task Contracts

<a id="task-001-create-project-init-skill"></a>

### TASK-001: Create project init skill

Goal: Add the repo-local skill that guides project-specific Harness initialization.

Files:
- Create: `.harness/skills/project-init/SKILL.md`
- Create: `.harness/tests/test_project_init_skill.py`

Depends on: []

Acceptance:
- The skill frontmatter has `name: project-init` and a trigger description for initializing Harness in a target development repository.
- The skill requires repository evidence review before asking user questions.
- The skill separates Harness core checks from project environment checks.
- The skill requires project contracts before any custom check script or adapter.
- The skill forbids writing `workflow-state.json` directly and forbids adding project-specific checks to `session-start.py`.

Verification:
- Run: `python3 .harness/tests/test_project_init_skill.py`
- Check: the skill body names project profile, environment checks, command registry, blocking/warning severity, and adapter fallback.

<a id="task-002-gate-project-init-skill-asset"></a>

### TASK-002: Gate project init skill asset

Goal: Make `session-start.py` treat the project-init skill as a required Harness asset.

Files:
- Modify: `.harness/scripts/session-start.py`
- Modify: `.harness/tests/test_session_start.py`

Depends on: [TASK-001]

Acceptance:
- Session startup preflight reports `.harness/skills/project-init/SKILL.md` when that skill is missing.
- Test fixtures copy the new required skill asset into temporary Harness roots.
- `session-start.py` still checks only Harness assets and does not add project-specific environment checks.

Verification:
- Run: `python3 .harness/tests/test_session_start.py`
- Check: the missing asset assertion names `.harness/skills/project-init/SKILL.md`.

<a id="task-003-document-project-init-skill"></a>

### TASK-003: Document project init skill

Goal: Document where the project-init skill sits in the Harness architecture.

Files:
- Modify: `harness-design/architecture.md`
- Test: `.harness/tests/test_session_start.py`
- Test: `.harness/tests/test_project_init_skill.py`

Depends on: [TASK-001, TASK-002]

Acceptance:
- The architecture overview lists `.harness/skills/project-init/SKILL.md`.
- The architecture text states that project environment differences belong in project contracts, not in `session-start.py`.
- The architecture text keeps `.harness/` as the contract/tooling layer and `work/` as runtime data.

Verification:
- Run: `python3 .harness/tests/test_session_start.py`
- Run: `python3 .harness/tests/test_project_init_skill.py`
- Run: `python3 .harness/scripts/lint-harness.py --root .`
- Check: `harness-design/architecture.md` describes project initialization without changing workflow truth-source semantics.
