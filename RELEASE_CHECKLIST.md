# Publication checklist

Status reflects the current workspace state as of 2026-08-14.

## Completed for release readiness

- [x] Core package implemented with typed public API and release docs.
- [x] Package metadata includes final public GitHub URLs in `pyproject.toml`.
- [x] PyPI exact-name check for `tooltether` returned HTTP `404` on 2026-08-14.
- [x] CI badge added to `README.md`.
- [x] Public README no longer contains corrupted null bytes or pre-publication name wording.
- [x] Python 3.11 callable-instance and stdlib `TypedDict` compatibility regressions fixed and covered.
- [x] Current local test suite passes with coverage above the configured `90%` gate.
- [x] Ruff and mypy pass locally.
- [x] Live `pip-audit` final result on 2026-08-14: `No known vulnerabilities found`; expected skip note remains because `tooltether 0.1.0` is not on PyPI yet.
- [x] `mkdocs build --strict`, `python -m build`, and `python -m twine check dist/*` pass locally.
- [x] Final wheel installs in a fresh environment and passes import, CLI, runtime, and OpenAI export smoke checks.
- [x] Final wheel and sdist SHA-256 hashes were generated after the latest source edits.
- [x] Tracked `.pip-audit-cache` artifacts are scheduled for removal from version control.

## Required immediately before public release

- [ ] Obtain explicit repository-owner authorization before any publish step.
- [ ] Confirm GitHub private vulnerability reporting or another private security contact is enabled.
- [ ] Confirm PyPI Trusted Publisher for `.github/workflows/release.yml` with environment `release`.
- [ ] Confirm TestPyPI Trusted Publisher for `.github/workflows/testpypi.yml` with environment `testpypi`.
- [ ] Run the final GitHub Actions CI matrix for Python `3.11`, `3.12`, `3.13`, and `3.14` on Ubuntu, Windows, and macOS.
- [ ] Run the optional compatibility workflow for public extras.
- [ ] Run final local checks from a clean tree:
  - `ruff format --check .`
  - `ruff check .`
  - `mypy src`
  - `python -m pytest --cov=tooltether`
  - `mkdocs build --strict`
  - `bandit -q -r src`
  - `python -m pip check`
  - `pip-audit`
  - `python -m build`
  - `python -m twine check dist/*`
- [ ] Install the final wheel in a fresh environment and smoke-test import, CLI, and adapter export.
- [ ] Regenerate `dist/SHA256SUMS` from the final tagged release build.
- [ ] Copy the exact final wheel and sdist hashes into the GitHub Release notes.
- [ ] Verify published artifacts, hashes, provenance, and install path after PyPI upload.

## Do not do yet

- [ ] Do not publish to PyPI without explicit owner approval.
- [ ] Do not create a release tag until final CI, audit, build, and smoke checks are green.
- [ ] Do not store a long-lived PyPI API token; use Trusted Publishing / OIDC.
