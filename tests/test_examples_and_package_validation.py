from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validate_package import main as validate_package_main

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "example",
    (
        "examples/basic_usage.py",
        "examples/typed_tool.py",
        "examples/async_usage.py",
        "examples/execution_policy.py",
    ),
)
def test_public_examples_run(example: str) -> None:
    subprocess.run([sys.executable, str(ROOT / example)], cwd=ROOT, check=True)  # noqa: S603


def test_package_content_validator_reports_missing_dist(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="expected exactly one wheel"):
        validate_package_main(["--dist-dir", str(tmp_path)])
