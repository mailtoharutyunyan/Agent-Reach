# Releasing WebLens

Releases are automated by `.github/workflows/release.yml`. Pushing a `vX.Y.Z` tag
builds the sdist and wheel, checks that the tag matches the package version,
publishes to PyPI through trusted publishing (no API token), and creates a GitHub
Release with the built files attached.

## One-time setup

### 1. Replace the GitHub placeholder

The repo uses `YOUR_GITHUB_USER` as a placeholder in URLs. Replace it with your
GitHub username or org (for example `octocat`):

```bash
# macOS (BSD sed)
grep -rlI YOUR_GITHUB_USER --exclude-dir=.git --exclude-dir=.venv --exclude=RELEASING.md . | xargs sed -i '' 's/YOUR_GITHUB_USER/octocat/g'

# Linux (GNU sed)
grep -rlI YOUR_GITHUB_USER --exclude-dir=.git --exclude-dir=.venv --exclude=RELEASING.md . | xargs sed -i 's/YOUR_GITHUB_USER/octocat/g'
```

Then confirm nothing is left and the tests still pass:

```bash
grep -rI YOUR_GITHUB_USER --exclude-dir=.git --exclude-dir=.venv --exclude=RELEASING.md . || echo "clean"
pytest -q
```

### 2. Create the GitHub repository and push

```bash
gh repo create octocat/weblens --public --source . --remote origin
git push -u origin main
```

(Or create an empty `weblens` repo on github.com, then
`git remote add origin git@github.com:octocat/weblens.git && git push -u origin main`.)

### 3. Create the `pypi` environment on GitHub

Go to repo **Settings → Environments → New environment** and name it `pypi`.
Adding yourself as a required reviewer is optional but recommended: each
publish then waits for your approval.

### 4. Configure the PyPI trusted publisher

The project doesn't exist on PyPI yet, so add a *pending* publisher. On
<https://pypi.org/manage/account/publishing/>, under **Add a new pending
publisher → GitHub**, enter:

| Field             | Value         |
|-------------------|---------------|
| PyPI Project Name | `weblens`     |
| Owner             | `octocat`     |
| Repository name   | `weblens`     |
| Workflow name     | `release.yml` |
| Environment name  | `pypi`        |

The first successful release creates the project and turns the pending
publisher into a normal one. Later releases need no PyPI changes.

## Every release

### 1. Bump the version

The version is defined once, in `weblens/__init__.py`:

```python
__version__ = "1.1.0"
```

`pyproject.toml` reads it from there (`[tool.hatch.version]`), and the CLI,
User-Agent and update check all import it. Nothing else needs to change.

### 2. Update the changelog

Add a `## [1.1.0] - YYYY-MM-DD` section at the top of `CHANGELOG.md`.

### 3. Verify locally

```bash
pytest -q
ruff check weblens tests
mypy weblens
python -m build && twine check --strict dist/* && rm -rf dist build
```

### 4. Commit, tag and push

```bash
git commit -am "Release v1.1.0"
git push origin main
git tag v1.1.0
git push origin v1.1.0
```

Pushing the tag starts the `release` workflow. If you added a reviewer to the
`pypi` environment, approve the deployment in the Actions tab. When it finishes,
the new version is on <https://pypi.org/project/weblens/> and has a release page
on GitHub.

## If something goes wrong

- **Tag/version mismatch:** the build job fails before anything is published.
  Delete the tag (`git tag -d v1.1.0 && git push origin :refs/tags/v1.1.0`),
  fix `__version__`, and tag again.
- **PyPI publish failed:** check the trusted publisher fields above. They must
  match exactly, including the `pypi` environment name. Re-run the failed job
  from the Actions tab.
- **A bad release reached PyPI:** PyPI never lets you reuse a version number.
  Yank it on PyPI (Manage → Releases → Yank), then release a fixed `X.Y.Z+1`.
