# Release process

This project is currently prepared as `tooltether` version `0.1.0` for an alpha release. The steps below are tailored to the current repository state as of July 18, 2026.

## Current verified state

| Area | Status | Notes |
|---|---|---|
| Local tests | Complete | `68 passed` with `90.52%` coverage |
| Static analysis | Complete | Ruff, mypy, and Bandit passed |
| Documentation build | Complete | `mkdocs build --strict` passed |
| Packaging | Complete | Wheel and sdist built, `twine check` passed |
| Clean install smoke | Complete | Wheel installed in `.venv-wheel`; import, CLI, and OpenAI export smoke passed |
| Artifact hashes | Complete | Final hashes should be recorded immediately after each release build in `dist/SHA256SUMS` and the GitHub Release notes |
| Live dependency audit | Complete with finding | `pip-audit --local --cache-dir .pip-audit-cache` found four advisories on local dev-environment `pip 26.0.1`; fixes available in `26.1` and `26.1.2` |
| Final owner/repository metadata | Pending | Public URLs and maintainer-controlled contacts still need final values |
| Cross-version/extras execution | Pending | Declared support is Python `3.11-3.14`, but only `3.14.4` was executed locally |
| Publication authorization | Pending | No public release should occur without repository-owner approval |

## Final local evidence

- `pytest --cov=src/tooltether --cov-report=term-missing`
- `ruff check .`
- `ruff format --check .`
- `mypy src`
- `mkdocs build --strict`
- `bandit -q -r src`
- `python -m pip check`
- `pip-audit --local --cache-dir .pip-audit-cache`
- `python -m build --no-isolation`
- `twine check dist/*`

## Release gating sequence

1. Confirm that `ToolTether` / `tooltether` is the final public name and that the repository owner accepts the naming and legal risk.
2. Set final repository metadata:
   - add `[project.urls]` values in `pyproject.toml`
   - confirm `NOTICE`, `LICENSE`, `CITATION.cff`, `SECURITY.md`, and `CODE_OF_CONDUCT.md`
   - ensure the public repository and release channel exist before linking them
3. Resolve or accept the current live dependency-audit finding before release. Current result:
   - audited environment: local development `.venv`
   - vulnerable package: `pip 26.0.1`
   - advisories: `PYSEC-2026-196` twice, `PYSEC-2026-2875`, `PYSEC-2026-2876`
   - fixed versions reported by PyPI: `26.1` and `26.1.2`
   - impact scope: development environment tooling, not the published `tooltether` runtime dependency set
4. Execute the GitHub Actions compatibility matrix for:
   - Python `3.11`, `3.12`, `3.13`, `3.14`
   - optional adapter extras that are intended to be supported publicly
5. Review all experimental adapters and decide whether their extras should ship in the first public alpha unchanged or be deferred.
6. Update the changelog and version if the owner wants a release number other than `0.1.0`.
7. Create a protected `v*` tag and require release-environment approval.
8. Publish using PyPI Trusted Publishing / OIDC only; do not create or store a long-lived upload token.
9. Verify the published artifacts, hashes, provenance, and install path from PyPI.

## Artifact recording rule

Record wheel and sdist SHA-256 values only after the final build is complete, and store them outside the source tree in:

- `dist/SHA256SUMS`
- the GitHub Release notes
- any signed provenance or attestation output

Do not treat hashes embedded in source-controlled documentation as authoritative for the final sdist, because the sdist contains that documentation and the value becomes self-invalidating.

## Known pre-publication constraints

- The project is honest alpha software, not yet a proven multi-version release.
- CrewAI, AutoGen, and smolagents adapters remain experimental.
- The core runtime does not sandbox arbitrary Python execution.
- The approved live dependency audit found four known vulnerabilities in local dev-environment `pip 26.0.1`; this should be remediated or consciously accepted before public release.
