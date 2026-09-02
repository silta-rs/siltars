# PyPI Release Preparation

Silta's Python distribution name is `siltars`. The Python import package and CLI
remain `silta`.

The first public package should be published as a pre-release, starting with
`0.1.0a0`, until native runtime wheels and reproducible benchmarks are ready.

## Before First Publish

1. Create a PyPI account for the maintainer.
2. Enable two-factor authentication on the PyPI account.
3. Configure Trusted Publishing for TestPyPI first:
   - TestPyPI project: `siltars`
   - owner/repository: `silta-rs/siltars`
   - workflow: `publish-testpypi.yml`
   - environment: `testpypi`
4. Configure Trusted Publishing for PyPI:
   - PyPI project: `siltars`
   - owner/repository: `silta-rs/siltars`
   - workflow: `publish-pypi.yml`
   - environment: `pypi`
5. Build and validate locally:

   ```bash
   python -m pip install --upgrade build twine
   python -m build --sdist --wheel
   python -m twine check dist/*
   ```

6. Test install in a clean virtual environment before announcing the package.

## Current Scope

The initial package is a Pre-Alpha distribution. It should not claim production
readiness, bundled native wheels, or benchmark-backed superiority until those
paths are implemented and reproduced.
