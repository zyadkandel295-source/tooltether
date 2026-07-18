# Publication checklist

Status reflects the current workspace state as of July 18, 2026.

## Already completed locally

- [x] Core package implemented with typed public API and release docs.
- [x] Local tests passed: `68 passed`, coverage `90.52%`.
- [x] `ruff check .` passed.
- [x] `ruff format --check .` passed.
- [x] `mypy src` passed.
- [x] `mkdocs build --strict` passed.
- [x] `bandit -q -r src` passed.
- [x] Secret / placeholder / `TODO|FIXME` cleanup completed for release metadata.
- [x] `python -m pip check` passed.
- [x] `python -m build --no-isolation` produced final wheel and sdist.
- [x] `twine check dist/*` passed.
- [x] Wheel installed in a clean environment and passed import, CLI, and OpenAI-export smoke tests.
- [x] Final SHA-256 checksums can be generated and recorded post-build outside the source tree.
- [x] Live `pip-audit` executed against PyPI and recorded.

## Required before public release

- [ ] Confirm `ToolTether` / `tooltether` is the final public package and repository name.
- [ ] Set final public repository URLs in `pyproject.toml`.
- [ ] Confirm maintainer-facing contact details and release channel wording in `SECURITY.md` and `CODE_OF_CONDUCT.md`.
- [ ] Decide how to handle the recorded `pip-audit` finding on local dev-environment `pip 26.0.1`:
  - advisories `PYSEC-2026-196`, `PYSEC-2026-196`, `PYSEC-2026-2875`, `PYSEC-2026-2876`
  - reported fixes `26.1` / `26.1.2`
  - scope is the development environment, not ToolTether's declared runtime dependency list
- [ ] Execute CI compatibility runs for Python `3.11`, `3.12`, and `3.13` in addition to the local `3.14.4` run.
- [ ] Execute the intended optional-extra matrix for public support claims.
- [ ] Reconfirm whether experimental adapters should all remain enabled in the first public alpha.
- [ ] Approve changelog and final version/tag.
- [ ] Configure PyPI Trusted Publisher and GitHub release attestation flow.
- [ ] Verify protected release environment and owner approval path.
- [ ] Obtain explicit repository-owner authorization before any publish step.

## Artifact record

- [ ] Generate `dist/SHA256SUMS` from the final release build.
- [ ] Copy the exact wheel and sdist hashes into the GitHub Release notes.
- [ ] Verify that the hashes cited publicly were generated after the final source-controlled release note edits.
