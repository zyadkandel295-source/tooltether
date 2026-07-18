from pathlib import Path
from tempfile import TemporaryDirectory

from tooltether import ExecutionIdentity, Policy, Runtime, tool


@tool(side_effects="write", permissions=["filesystem:write"], idempotent=True)
def save_report(path: str, content: str) -> str:
    """Save a report under an approved temporary workspace."""
    Path(path).write_text(content, encoding="utf-8")
    return path


if __name__ == "__main__":
    with TemporaryDirectory() as workspace:
        policy = Policy()
        policy.allow(tool="save_report", resources=("reports/**",), rule_id="reports-only")
        target = Path(workspace, "reports", "report.txt")
        target.parent.mkdir()
        identity = ExecutionIdentity(principal="example", workspace=workspace)
        print(
            Runtime(policy=policy)
            .run(
                save_report,
                {"path": str(target), "content": "safe"},
                identity=identity,
            )
            .value
        )
