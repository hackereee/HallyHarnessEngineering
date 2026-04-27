# Session project-contracts-runner

## Summary

Implemented PLAN-004 to prevent generated check-script drift by making `.harness/contracts/project-contracts.json` the project environment truth source and `.harness/scripts/check-project-env.py` a generic read-only runner.

## Delivered

- Project contracts schema and template.
- Generic project environment checker runner.
- Harness CLI subcommand `check-project-env`.
- Session-start required asset gating for runner/schema/template without executing project checks.
- Updated project-init skill and architecture documentation.

## Verification Evidence

- `python3 .harness/tests/test_project_contracts_schema.py` passed.
- `python3 .harness/tests/test_check_project_env.py` passed.
- `python3 .harness/tests/test_harness_cli.py` passed.
- `python3 .harness/tests/test_session_start.py` passed.
- `python3 .harness/tests/test_project_init_skill.py` passed.
- `python3 .harness/scripts/lint-harness.py --root .` passed.
- `python3 .harness/scripts/check-project-env.py --root . --contract .harness/templates/project-contracts.template.json --schema .harness/schemas/project-contracts.schema.json` passed.

## Review Summary

- TASK-001 passed review with score 92 and no findings.
- TASK-002 passed review with score 91 and no findings.
- TASK-003 passed review with score 93 and no findings.
- The final design keeps project checks contract-first: the runner validates and executes declared checks, while `session-start.py` only verifies Harness assets.
