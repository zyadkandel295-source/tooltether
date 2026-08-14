"""Cross-platform local release-readiness checks for ToolTether."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-audit", action="store_true", help="Skip networked pip-audit")
    parser.add_argument("--skip-installed-smoke", action="store_true")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    commands: list[list[str]] = [
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "mypy", "src"],
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=tooltether",
            "--basetemp=.pytest_tmp_release",
        ],
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        [sys.executable, "-m", "bandit", "-q", "-r", "src"],
        [sys.executable, "-m", "pip", "check"],
    ]
    if not args.skip_audit:
        commands.append([sys.executable, "-m", "pip_audit"])
    for command in commands:
        _run(command, root)

    for path in (root / "build", root / "dist"):
        if path.exists():
            shutil.rmtree(path)
    _run([sys.executable, "-m", "build"], root)
    wheel = _single((root / "dist").glob("*.whl"), "wheel")
    sdist = _single((root / "dist").glob("*.tar.gz"), "sdist")
    _run([sys.executable, "-m", "twine", "check", str(wheel), str(sdist)], root)
    _run([sys.executable, "scripts/validate_package.py"], root)
    if not args.skip_installed_smoke:
        examples = [
            "examples/basic_usage.py",
            "examples/typed_tool.py",
            "examples/async_usage.py",
            "examples/execution_policy.py",
        ]
        _run(
            [
                sys.executable,
                "scripts/installed_package_smoke.py",
                str(wheel),
                *_examples_args(examples),
            ],
            root,
        )
        _run([sys.executable, "scripts/installed_package_smoke.py", str(sdist)], root)
    print("release checks PASS")
    return 0


def _examples_args(examples: list[str]) -> list[str]:
    return ["--examples", *examples]


def _single(paths: object, label: str) -> Path:
    values = sorted(paths)  # type: ignore[arg-type]
    if len(values) != 1:
        raise SystemExit(f"expected exactly one {label}, found {len(values)}")
    return values[0]


def _run(command: list[str], cwd: Path) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)  # noqa: S603


if __name__ == "__main__":
    raise SystemExit(main())
