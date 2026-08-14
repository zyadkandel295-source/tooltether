# Release process

This project is prepared as `tooltether` version `0.1.0` for an alpha PyPI release. This checklist reflects the repository state as of 2026-08-14.

## Current verified state

| Area | Status | Notes |
|---|---|---|
| Package metadata | Complete | `pyproject.toml` includes name, version, license expression, Python classifiers, keywords, project URLs, and explicit optional extras |
| PyPI name check | Complete | `https://pypi.org/pypi/tooltether/json` returned HTTP `404` on 2026-08-14 |
| Local tests | Complete | Current local suite is `76 passed`; coverage gate reaches at least `90%` |
| Static analysis | Complete | Ruff and mypy pass locally |
| Documentation build | Complete locally | `mkdocs build --strict` passed |
| Packaging | Complete locally | `python -m build` produced wheel and sdist; `twine check dist/*` passed |
| Clean install smoke | Complete locally | Final wheel installed in `.venv-wheel`; import, CLI `version`, runtime execution, and OpenAI schema export passed |
| Security checks | Complete locally | `bandit -q -r src` passed; live `pip-audit` returned no known vulnerabilities after upgrading the local dev-environment `cryptography` package to `50.0.0` |
| Artifact hashes | Complete locally | Final SHA-256 values were generated after the latest source-controlled edits and should be copied into GitHub Release notes at release time |
| Publication authorization | Pending | Do not publish without explicit repository-owner approval |

## Final local evidence commands

Run these from a clean checkout immediately before creating a release tag:

```bash
ruff format --check .
ruff check .
mypy src
python -m pytest --cov=tooltether
mkdocs build --strict
bandit -q -r src
python -m pip check
pip-audit
python -m build
python -m twine check dist/*
```

## Latest live dependency audit

Command run on 2026-08-14 from the local release virtual environment:

```text
.\.venv\Scripts\pip-audit.exe
```

Exact final result:

```text
No known vulnerabilities found
Name       Skip Reason
---------- -------------------------------------------------------------------------
tooltether Dependency not found on PyPI and could not be audited: tooltether (0.1.0)
```

Earlier in the same pass, `pip-audit` reported `cryptography 49.0.0` with advisory `PYSEC-2026-3552`, fixed in `50.0.0`. The local release virtual environment was upgraded to `cryptography 50.0.0`, and the audit was rerun successfully with the result above.

## Release gating sequence

1. Confirm repository-owner approval for publishing `tooltether` version `0.1.0`.
2. Confirm GitHub repository settings:
   - Actions enabled.
   - Branch protection or release-review process enabled for `main`.
   - Private vulnerability reporting enabled, or another private security contact documented.
   - Release and TestPyPI environments configured for Trusted Publishing.
3. Confirm PyPI / TestPyPI Trusted Publisher configuration:
   - Owner: `zyadkandel295-source`
   - Repository: `tooltether`
   - Workflow: `.github/workflows/release.yml` for PyPI
   - Workflow: `.github/workflows/testpypi.yml` for TestPyPI
   - Environment names: `release` and `testpypi`
4. Run the full CI matrix for Python `3.11`, `3.12`, `3.13`, and `3.14` across Ubuntu, Windows, and macOS.
5. Run optional compatibility workflow for public extras.
6. Review experimental adapters and keep their README status as `Experimental` unless installed-SDK matrices justify stronger wording.
7. Build final artifacts from the exact tagged source.
8. Generate `dist/SHA256SUMS` and include those hashes in the GitHub Release notes.
9. Publish through PyPI Trusted Publishing / OIDC only. Do not create or store a long-lived PyPI upload token.
10. Verify the published package page, install path, hashes, and provenance from PyPI.

## Artifact recording rule

Record wheel and sdist SHA-256 values only after the final build is complete, and store them outside the source tree in:

- `dist/SHA256SUMS`
- the GitHub Release notes
- any signed provenance or attestation output

Do not treat hashes embedded in source-controlled documentation as authoritative for the final sdist, because the sdist contains that documentation and the value becomes self-invalidating.

## Known alpha constraints

- ToolTether is honest alpha software.
- CrewAI, AutoGen, and smolagents adapters remain experimental.
- The core runtime does not sandbox arbitrary Python execution.
- Transport authorization, provider credentials, process isolation, and remote service permissions remain host-application responsibilities.
