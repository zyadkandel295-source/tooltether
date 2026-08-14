"""Run external-user smoke tests against a built ToolTether artifact."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="Wheel or sdist to install")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--keep-env", action="store_true")
    parser.add_argument("--examples", nargs="*", default=())
    args = parser.parse_args(argv)

    artifact = Path(args.artifact).resolve()
    repo_root = Path(args.repo_root).resolve()
    if not artifact.exists():
        raise SystemExit(f"artifact not found: {artifact}")

    workdir = Path(tempfile.mkdtemp(prefix="tooltether-installed-smoke-")).resolve()
    env_dir = workdir / "venv"
    try:
        _run([args.python, "-m", "venv", str(env_dir)], cwd=workdir)
        python = _venv_python(env_dir)
        _run([str(python), "-m", "pip", "install", str(artifact)], cwd=workdir)
        _run([str(python), "-m", "pip", "check"], cwd=workdir)
        _run([str(python), "-m", "pip", "uninstall", "-y", "tooltether"], cwd=workdir)
        _run([str(python), "-m", "pip", "install", str(artifact)], cwd=workdir)
        _run([str(python), "-m", "pip", "check"], cwd=workdir)
        metadata = _run(
            [str(python), "-m", "pip", "show", "tooltether"],
            cwd=workdir,
            capture=True,
        )
        print(metadata.stdout.strip())
        output = _run(
            [str(python), "-c", _external_user_program(repo_root)],
            cwd=workdir,
            capture=True,
        )
        print(output.stdout.strip())
        for example in args.examples:
            _run([str(python), str((repo_root / example).resolve())], cwd=workdir)
        print(f"{artifact.name}: installed-package smoke PASS")
    finally:
        if args.keep_env:
            print(f"kept smoke environment: {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)
    return 0


def _venv_python(env_dir: Path) -> Path:
    if os.name == "nt":
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def _run(
    command: list[str],
    *,
    cwd: Path,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        cwd=cwd,
        text=True,
        check=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def _external_user_program(repo_root: Path) -> str:
    repo = repo_root.as_posix()
    return textwrap.dedent(
        f"""
        import asyncio
        import pathlib

        import tooltether
        from tooltether import (
            ExecutionMode,
            ExecutionPolicy,
            ExecutionPolicyError,
            Runtime,
            ToolDefinitionError,
            ToolRegistry,
            ToolValidationError,
            MissingExtraError,
            tool,
        )

        installed = pathlib.Path(tooltether.__file__).resolve()
        assert str(installed).replace('\\\\', '/').startswith('{repo}') is False, installed
        assert tooltether.__version__ == '0.1.0'

        @tool
        def add(a: int, b: int) -> int:
            '''Add two integers.'''
            return a + b

        runtime = Runtime()
        assert runtime.run(add, {{'a': 2, 'b': 3}}).value == 5
        assert add.export('openai')['type'] == 'function'
        try:
            add.export('langchain', runtime=runtime)
        except MissingExtraError as exc:
            assert 'tooltether[langchain]' in str(exc)
        else:
            raise AssertionError('base install should not include optional langchain extra')

        @tool
        def calculate_total(price: float, quantity: int, discount: float = 0.0) -> float:
            '''Calculate a discounted line total.'''
            return price * quantity * (1 - discount)

        assert runtime.run(calculate_total, {{'price': 10.0, 'quantity': 3}}).value == 30.0
        assert runtime.run(
            calculate_total, {{'price': 10.0, 'quantity': 3, 'discount': 0.1}}
        ).value == 27.0
        assert 'discount' in calculate_total.spec.input_schema['properties']

        registry = ToolRegistry()
        registry.register(add)
        try:
            registry.register(add)
        except ToolDefinitionError:
            pass
        else:
            raise AssertionError('duplicate registration should fail')

        try:
            registry.get('missing')
        except KeyError:
            pass
        else:
            raise AssertionError('unknown tool should fail')

        try:
            runtime.run(add, {{'a': 1}})
        except ToolValidationError as exc:
            assert exc.code == 'tool_validation_error'
        else:
            raise AssertionError('missing argument should fail')

        restricted = Runtime(execution_policy=ExecutionPolicy(mode=ExecutionMode.RESTRICTED))
        assert restricted.run(add, {{'a': 1, 'b': 2}}).value == 3

        @tool(side_effects='write', permissions=['records:write'])
        def mutate() -> str:
            '''Mutate a fake record.'''
            return 'mutated'

        try:
            restricted.run(mutate, {{}})
        except ExecutionPolicyError:
            pass
        else:
            raise AssertionError('restricted policy should reject writes')

        @tool
        async def async_add(a: int, b: int) -> int:
            '''Add two integers asynchronously.'''
            await asyncio.sleep(0)
            return a + b

        async def async_main() -> None:
            assert (await runtime.arun(async_add, {{'a': 4, 'b': 5}})).value == 9
            values = await asyncio.gather(
                *(runtime.arun(add, {{'a': i, 'b': 1}}) for i in range(25))
            )
            assert [item.value for item in values] == [i + 1 for i in range(25)]

        asyncio.run(async_main())

        for i in range(200):
            assert runtime.run(add, {{'a': i, 'b': 1}}).value == i + 1

        print('version=' + tooltether.__version__)
        print('file=' + str(installed))
        print(
            'basic=PASS typed=PASS async=PASS errors=PASS policy=PASS '
            'optional_deps=PASS repeated=200/200'
        )
        """
    )


if __name__ == "__main__":
    raise SystemExit(main())
