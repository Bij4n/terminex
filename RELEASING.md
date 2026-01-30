# Releasing terminex to PyPI

One-time setup on the release machine:

```bash
python3 -m pip install --user build twine
```

Create an account at https://pypi.org, generate an API token with
`project:terminex` scope, and store it in `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-YOUR-TOKEN-HERE
```

## Cutting a release

1. Make sure `main` is green on CI and all changes you want in the
   release are merged.
2. Bump `version` in `pyproject.toml` (follow semver:
   breaking → major, new feature → minor, bug fix → patch).
3. Commit the bump:
   ```bash
   git commit -am "bump version to X.Y.Z"
   ```
4. Tag the release:
   ```bash
   git tag -a vX.Y.Z -m "terminex X.Y.Z"
   git push origin main --tags
   ```
5. Build and upload:
   ```bash
   rm -rf dist/ build/ *.egg-info/
   python3 -m build
   python3 -m twine upload dist/*
   ```
6. Verify: `pipx install terminex==X.Y.Z` should pull from PyPI.

## Test release (recommended before the real thing)

Use TestPyPI for a dry-run:

```bash
python3 -m twine upload --repository testpypi dist/*
pipx install --index-url https://test.pypi.org/simple/ terminex
```
