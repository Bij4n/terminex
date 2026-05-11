# Releasing terminex

Releases are fully automated via GitHub Actions. Pushing a version tag
triggers a build and publishes to PyPI using OIDC (no stored API token
needed).

## One-time PyPI setup (do this once before the first release)

1. Create an account at https://pypi.org if you don't have one.
2. Go to **Your projects → Add project** and reserve the `terminex` name
   by creating an empty project, or it will be created automatically on
   first publish.
3. Go to **Account settings → Publishing → Add a new pending publisher**
   and fill in:
   - PyPI project name: `terminex`
   - Owner: `Bij4n`
   - Repository name: `terminex`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`
4. In the GitHub repository, go to **Settings → Environments → New
   environment** and create one named `pypi`. No secrets or protection
   rules are required — the OIDC trust is configured on the PyPI side.

## Cutting a release

1. Make sure `main` is green on CI and all changes are merged.
2. Bump `version` in `pyproject.toml` (semver: breaking → major,
   new feature → minor, bug fix → patch).
3. Commit the bump:
   ```bash
   git commit -am "bump version to X.Y.Z"
   git push
   ```
4. Tag and push:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
5. The `publish` GitHub Actions workflow runs automatically, builds the
   wheel and sdist, and uploads to PyPI.
6. Verify: `pipx install terminex==X.Y.Z` should pull from PyPI within
   a minute or two of the workflow completing.

## Dry run on TestPyPI (optional)

Add a second Trusted Publisher on https://test.pypi.org with the same
settings, then temporarily point the workflow's publish step at TestPyPI:

```yaml
- uses: pypa/gh-action-pypi-publish@release/v1
  with:
    repository-url: https://test.pypi.org/legacy/
```

Then verify with:

```bash
pipx install --index-url https://test.pypi.org/simple/ terminex
```
