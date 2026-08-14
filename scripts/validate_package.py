"""Validate ToolTether wheel and sdist contents before publication."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_PARTS = {
    ".coverage",
    ".git",
    ".mypy_cache",
    ".pip-audit-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv-wheel",
    ".venv311",
    "__pycache__",
    "build",
    "dist",
    "site",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", default="dist")
    args = parser.parse_args(argv)
    dist = Path(args.dist_dir)
    wheel = _single(dist.glob("tooltether-*.whl"), "wheel")
    sdist = _single(dist.glob("tooltether-*.tar.gz"), "sdist")
    _validate_wheel(wheel)
    _validate_sdist(sdist)
    print(f"validated package contents: {wheel.name}, {sdist.name}")
    return 0


def _single(paths: object, label: str) -> Path:
    values = sorted(paths)  # type: ignore[arg-type]
    if len(values) != 1:
        raise SystemExit(f"expected exactly one {label}, found {len(values)}")
    return values[0]


def _validate_wheel(path: Path) -> None:
    names = _zip_names(path)
    _require(names, "tooltether/__init__.py", path)
    _require(names, "tooltether/py.typed", path)
    _require_suffix(names, ".dist-info/METADATA", path)
    _require_suffix(names, ".dist-info/WHEEL", path)
    _reject_junk(names, path)
    metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
    with zipfile.ZipFile(path) as archive:
        metadata = archive.read(metadata_name).decode("utf-8")
    for expected in (
        "Name: tooltether",
        "Version: 0.1.0",
        "Requires-Python: >=3.11",
        "License-Expression: Apache-2.0",
        "Requires-Dist: pydantic",
    ):
        if expected not in metadata:
            raise SystemExit(f"{path.name} metadata missing {expected!r}")


def _validate_sdist(path: Path) -> None:
    names = _tar_names(path)
    prefix = _sdist_prefix(names, path)
    for expected in (
        "LICENSE",
        "README.md",
        "pyproject.toml",
        "src/tooltether/__init__.py",
        "src/tooltether/py.typed",
        "tests/test_core.py",
        "examples/basic_usage.py",
        "scripts/validate_package.py",
    ):
        _require(names, f"{prefix}/{expected}", path)
    _reject_junk(names, path)


def _zip_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def _tar_names(path: Path) -> set[str]:
    with tarfile.open(path, "r:gz") as archive:
        return set(archive.getnames())


def _sdist_prefix(names: set[str], path: Path) -> str:
    prefixes = {name.split("/", 1)[0] for name in names if "/" in name}
    if len(prefixes) != 1:
        raise SystemExit(f"{path.name} should contain one top-level directory")
    return prefixes.pop()


def _require(names: set[str], expected: str, path: Path) -> None:
    if expected not in names:
        raise SystemExit(f"{path.name} missing expected file: {expected}")


def _require_suffix(names: set[str], suffix: str, path: Path) -> None:
    if not any(name.endswith(suffix) for name in names):
        raise SystemExit(f"{path.name} missing expected suffix: {suffix}")


def _reject_junk(names: set[str], path: Path) -> None:
    for name in names:
        parts = set(Path(name).parts)
        forbidden = sorted(parts.intersection(FORBIDDEN_PARTS))
        if forbidden:
            raise SystemExit(f"{path.name} contains forbidden path part {forbidden[0]!r}: {name}")
        if name.endswith((".pyc", ".pyo", ".db")):
            raise SystemExit(f"{path.name} contains generated/local file: {name}")


if __name__ == "__main__":
    raise SystemExit(main())
