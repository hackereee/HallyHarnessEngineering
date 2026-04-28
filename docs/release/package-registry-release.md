# Package Registry Release

This document defines the operator workflow for publishing the `hally-harness-engineering` package to TestPyPI or PyPI. Publishing is an external release operation and not a Harness runtime workflow gate.

## Registry Setup

Use PyPI Trusted Publisher configuration for GitHub Actions. Configure the publisher on the target registry with:

- repository owner and repository name;
- workflow filename: `publish-python-package.yml`;
- environment name: `pypi` for production PyPI promotion;
- matching TestPyPI publisher configuration for TestPyPI validation.

The workflow uses GitHub OIDC and `pypa/gh-action-pypi-publish@release/v1`. It requires job-level `id-token: write` and must not use `PYPI_TOKEN`, passwords, or long-lived registry credentials.

Reference:

- https://docs.pypi.org/trusted-publishers/using-a-publisher/
- https://docs.pypi.org/trusted-publishers/adding-a-publisher/
- https://github.com/pypa/gh-action-pypi-publish

## Local Release Gates

Before triggering `.github/workflows/publish-python-package.yml`, run the local gates:

```bash
python3 -m unittest discover -s installer/tests -p 'test_*.py'
python3 -m build
python3 installer/release/check_artifacts.py dist
python3 installer/release/smoke_install.py dist
```

These gates prove the tests, built distributions, wheel metadata, console script, bundled `.harness/` payload, and installed CLI behavior before any registry upload.

## Version Bump

PyPI and TestPyPI versions are immutable after upload. Before publication:

1. Choose the next version in `pyproject.toml`.
2. Run the local release gates.
3. Commit the version bump and release workflow changes.
4. Tag the release only after TestPyPI validation passes.

Do not attempt to repair a bad upload by reusing the same version. Bump to a new version and publish again.

## TestPyPI Validation

Trigger `Publish Python Package` manually with `registry = testpypi`.

After the workflow succeeds, validate installation from TestPyPI in a clean environment:

```bash
python3 -m venv /tmp/harness-testpypi
/tmp/harness-testpypi/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  hally-harness-engineering==<version>
/tmp/harness-testpypi/bin/hally-harness-engineering --help
```

Use the extra PyPI index for dependencies that may not exist on TestPyPI.

## PyPI Promotion

Trigger `Publish Python Package` manually with `registry = pypi`. The PyPI job is gated by the `pypi` GitHub environment and publishes only when the explicit `pypi` input is selected.

After promotion, validate user-facing tool installation:

```bash
pipx install hally-harness-engineering
pipx upgrade hally-harness-engineering
uv tool install hally-harness-engineering
uv tool upgrade hally-harness-engineering
```

Then run a minimal installed command check:

```bash
hally-harness-engineering --help
hally-harness-engineering install /tmp/harness-target --dry-run
```

## Rollback And Yank

Package registry rollback is forward-only:

- If a release is broken but should remain installable for existing pinned users, publish a fixed version and document the superseded version.
- If a release should not be selected by normal installers, yank the affected release on PyPI/TestPyPI and publish a fixed version.
- If a secret or credential was exposed, revoke it outside the repository, rotate affected credentials, and publish a fixed version if package contents changed.

Do not delete local Harness runtime state to recover from package registry mistakes. Registry publication remains outside the Harness runtime workflow.
