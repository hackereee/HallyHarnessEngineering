# TASK-001 Review: Add project-update skill

Plan: PLAN-014
Task: TASK-001
Reviewed At: 2026-06-06T21:21:00+08:00
Reviewer: harness-reviewer
Verdict: passed
Score: 92
Threshold: 85

## Scope Reviewed

- Added `.harness/skills/project-update/SKILL.md`.
- Updated `project-init` to defer already-onboarded synchronization to `project-update`.
- Documented `project-update` in Harness architecture and installer lifecycle.
- Added session startup core asset coverage for the new skill.
- Updated source tests, installer tests, fixed asset manifest, and installer payload.

## Verification Evidence

- `python3 .harness/tests/test_project_update_skill.py` passed.
- `python3 .harness/tests/test_project_init_skill.py` passed.
- `python3 .harness/tests/test_session_start.py` passed.
- `python3 installer/tests/test_install_lifecycle.py` passed.
- `python3 installer/tests/test_asset_manifest.py` passed.
- `python3 installer/tests/test_installer_engine.py` passed.
- `python3 .harness/tests/test_language_standardization.py` passed.
- `python3 -m unittest discover -s .harness/tests -p 'test_*.py'` passed with 210 tests.
- `python3 -m unittest discover -s installer/tests -p 'test_*.py'` passed with 41 tests.
- `python3 .harness/scripts/harness --root . validate-state` passed.
- `python3 .harness/scripts/lint-harness.py` passed.
- `rg -n "\p{Han}" .harness` reported no matches.
- `cmp -s .harness/skills/project-update/SKILL.md src/harness_engineering_installer/payload/.harness/skills/project-update/SKILL.md` passed.
- `git diff --check` reported no patch formatting issues.

## Review Checks

- Task acceptance is satisfied.
- Verification evidence is present and relevant.
- `project-update` clearly separates installer fixed asset copying from semantic managed block synchronization.
- Entrypoint writes remain restricted to `init-project-entrypoint.py` and the Harness managed block.
- User-owned prose outside the managed block is handled as reported recommendations, not automatic rewriting.
- Runtime state writes used Harness lifecycle gateways.
- Installer payload now matches source `.harness` fixed assets; the broad payload diff repairs previously detected manifest mismatches rather than introducing unrelated behavior.
- Architecture Impact is correct: root `ARCHITECTURE.md` remains unchanged; Harness framework architecture and installer lifecycle docs were intentionally updated.

## Findings

No blocking findings.
