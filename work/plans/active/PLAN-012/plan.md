# PLAN-012: Package Registry Release Workflow

## Background and Goal

PLAN-011 produced a packageable `harness-engineering` installer CLI and verified that local `python3 -m build` produces a wheel containing the fixed `.harness/` payload. The next release-level gap is not installer behavior; it is a reproducible package registry workflow that proves built artifacts, tests the installed command from the wheel, and gates TestPyPI/PyPI publication behind explicit operator control.

Goal: create a release workflow that can publish `harness-engineering` through TestPyPI/PyPI only after deterministic artifact inspection and installed-tool smoke tests pass.

## Scope

- Add deterministic checks for built `dist/` artifacts: package metadata, console script entry point, wheel/sdist presence, and bundled `.harness/` payload.
- Add an isolated installed-tool smoke test that installs the built wheel into a temporary virtual environment and exercises the CLI against a temporary target repository.
- Add a manual GitHub Actions release workflow for TestPyPI/PyPI publication using PyPI Trusted Publishing.
- Document release operation, install/upgrade commands, TestPyPI validation, PyPI promotion, and rollback/yank guidance.

## Non-Scope

- Do not publish to TestPyPI or PyPI during implementation.
- Do not add package registry credentials to the repository.
- Do not change installer runtime semantics unless a release check exposes a concrete defect.
- Do not move release concerns into `.harness/`; package publication remains an installer/distribution concern outside the runtime Harness framework.
- Do not model testing, review, or publishing approval as standalone tasks; they are workflow gates or release gates.

## Implementation Direction

Keep release automation outside `.harness/`. Put deterministic release helper scripts under `installer/release/` and their regression tests under `installer/tests/`. Use the existing package metadata in `pyproject.toml` as the source for package name and console script expectations. Use GitHub Actions only as a manual release gate: build, artifact inspection, installed-tool smoke test, then publish with PyPI Trusted Publishing.

Official packaging references checked during planning on 2026-04-28:

- PyPI Trusted Publishing: https://docs.pypi.org/trusted-publishers/using-a-publisher/
- PyPI trusted publisher setup: https://docs.pypi.org/trusted-publishers/adding-a-publisher/
- Python Packaging User Guide, build and publish: https://packaging.python.org/guides/section-build-and-publish/
- PyPA publish action: https://github.com/pypa/gh-action-pypi-publish

## File Boundaries

- Create: `installer/release/check_artifacts.py`
- Create: `installer/release/smoke_install.py`
- Create: `installer/tests/test_release_artifacts.py`
- Create: `installer/tests/test_release_smoke.py`
- Create: `installer/tests/test_release_docs.py`
- Create: `.github/workflows/publish-python-package.yml`
- Create: `docs/release/package-registry-release.md`
- Modify: `installer/install-lifecycle.md`
- Modify: `README.md`

## Task Decomposition

The plan is split by release risk boundary. TASK-001 proves build artifacts are structurally publishable. TASK-002 proves the published wheel would install and run as a user-facing tool. TASK-003 adds the external registry workflow and operator documentation after the local gates exist.

## Verification Strategy

Each task has a focused test file and a command that can be run locally before any registry interaction. The final task must also run Harness lint and workflow state validation because it adds GitHub workflow and release documentation, but it must not execute an actual publish.

## Architecture Impact

- Expected target project architecture impact: root `ARCHITECTURE.md` is absent in this repository and does not need to be introduced for release automation; README and release docs are the correct human-facing surfaces.
- Expected Harness framework architecture impact: `.harness/ARCHITECTURE.md` should remain unchanged unless implementation discovers that release tooling changes the Harness runtime framework boundary. Current expectation is no Harness framework architecture change.
- Expected installer architecture impact: `installer/install-lifecycle.md` should gain release gate language that distinguishes package publication from runtime installation and project initialization.

## Risks and Open Questions

- Risk: PyPI Trusted Publishing requires repository/environment configuration outside this repository; implementation must document the required PyPI-side setup and keep workflow publication manual.
- Risk: TestPyPI package names are global and may require a temporary alternate name if `harness-engineering` is unavailable there; implementation must document how to handle name collision without changing production package identity blindly.
- Risk: version numbers are immutable on PyPI once published; implementation must document version bump and recovery behavior before promotion.
- Open questions: none blocking for planning. Real publishing requires explicit user instruction after implementation and review.

## Plan Review Gate

Status: passed
Reviewer: codex-planner
Reviewed At: 2026-04-28T14:05:00+08:00

Checks:
- Scope, non-scope, file boundaries, dependencies, acceptance, and verification are reviewable.
- Tasks are delivery work units; testing, review, and publish approval remain gates.
- Release automation stays outside `.harness/` and does not alter runtime workflow state.
- Architecture Impact records target project, Harness framework, and installer lifecycle expectations.
- External registry publication is explicitly non-scope for implementation without later user instruction.

Findings:
- No blocking findings.

## Task Contracts

<a id="task-001-release-artifact-inspection"></a>

### TASK-001: Release artifact inspection

Goal: Add a deterministic artifact inspection script that validates locally built package distributions before any publish workflow can use them.

Files:
- Create: `installer/release/check_artifacts.py`
- Modify: `README.md`
- Test: `installer/tests/test_release_artifacts.py`

Depends on: []

Acceptance:
- The script accepts a `dist/` directory and requires exactly the expected `harness_engineering-<version>.tar.gz` source distribution and `harness_engineering-<version>-py3-none-any.whl` wheel for the version declared in `pyproject.toml`.
- The script verifies wheel metadata includes package name `harness-engineering`, console script `harness-engineering = harness_engineering_installer.cli:main`, and dependency `jsonschema>=4.18`.
- The script verifies the wheel includes `harness_engineering_installer/payload/.harness/ARCHITECTURE.md` and at least one schema, script, template, skill, and rule payload asset.
- The script fails with a non-zero exit code and a specific message when a required artifact, entry point, dependency, or payload asset is missing.
- README records the local artifact inspection command as a pre-publish release gate.

Verification:
- Run: `python3 installer/tests/test_release_artifacts.py`
- Run: `python3 -m build`
- Run: `python3 installer/release/check_artifacts.py dist`
- Check: `python3 installer/release/check_artifacts.py dist` reports package name, version, wheel, sdist, entry point, dependency, and payload checks.

<a id="task-002-installed-tool-smoke-test"></a>

### TASK-002: Installed tool smoke test

Goal: Add an isolated smoke test that installs the built wheel and verifies the user-facing CLI works outside the source tree.

Files:
- Create: `installer/release/smoke_install.py`
- Modify: `installer/install-lifecycle.md`
- Test: `installer/tests/test_release_smoke.py`

Depends on: [TASK-001]

Acceptance:
- The smoke script accepts a `dist/` directory, creates a temporary virtual environment, installs the local wheel, and runs the installed `harness-engineering` command from that environment.
- The smoke script runs `harness-engineering install <target> --dry-run` and confirms it writes nothing to the target.
- The smoke script runs `harness-engineering install <target>` and confirms `.harness/ARCHITECTURE.md` exists in the target.
- The smoke script runs `harness-engineering check <target>` and requires exit code 0 after installation.
- The smoke script creates a retired `.harness/rules/install-rules.md` asset, runs `harness-engineering update <target>`, and confirms that retired asset is pruned.
- `installer/install-lifecycle.md` records installed-tool smoke testing as a package release gate before TestPyPI/PyPI publication.

Verification:
- Run: `python3 installer/tests/test_release_smoke.py`
- Run: `python3 -m build`
- Run: `python3 installer/release/smoke_install.py dist`
- Check: the smoke target contains `.harness/ARCHITECTURE.md` after install and has no `.harness/rules/install-rules.md` after update.

<a id="task-003-registry-publish-workflow"></a>

### TASK-003: Registry publish workflow and docs

Goal: Add a manual package registry release workflow and operator documentation for TestPyPI validation and PyPI promotion.

Files:
- Create: `.github/workflows/publish-python-package.yml`
- Create: `docs/release/package-registry-release.md`
- Modify: `README.md`
- Modify: `installer/install-lifecycle.md`
- Test: `installer/tests/test_release_docs.py`

Depends on: [TASK-001, TASK-002]

Acceptance:
- The GitHub Actions workflow is manually triggered through `workflow_dispatch` and requires an explicit registry input for `testpypi` or `pypi`.
- The workflow runs installer tests, `python3 -m build`, `python3 installer/release/check_artifacts.py dist`, and `python3 installer/release/smoke_install.py dist` before any publish step.
- The workflow uses `pypa/gh-action-pypi-publish@release/v1` with job-level `permissions: id-token: write` and does not reference `PYPI_TOKEN` or password secrets.
- The TestPyPI publish step uses `repository-url: https://test.pypi.org/legacy/` and is separate from the PyPI publish step.
- The PyPI publish step is gated behind the explicit `pypi` input and a GitHub environment named `pypi`.
- Release docs explain PyPI/TestPyPI Trusted Publisher setup, version bump expectations, TestPyPI install validation, `pipx install`, `pipx upgrade`, `uv tool install`, `uv tool upgrade`, and rollback/yank guidance.
- Docs state that publishing is an external release operation and not a Harness runtime workflow gate.

Verification:
- Run: `python3 installer/tests/test_release_docs.py`
- Run: `python3 -m unittest discover -s installer/tests -p 'test_*.py'`
- Run: `python3 .harness/scripts/lint-harness.py --root .`
- Run: `python3 .harness/scripts/harness validate-state`
- Check: `.github/workflows/publish-python-package.yml` contains `workflow_dispatch`, `id-token: write`, `pypa/gh-action-pypi-publish@release/v1`, and `repository-url: https://test.pypi.org/legacy/`.
- Check: `.github/workflows/publish-python-package.yml` does not contain `PYPI_TOKEN` or `password:`.
