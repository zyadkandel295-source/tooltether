"""Trusted versus restricted execution policy behavior."""

from tooltether import ExecutionMode, ExecutionPolicy, ExecutionPolicyError, Runtime, tool


@tool
def read_value() -> str:
    """Read a safe local value."""
    return "safe"


@tool(side_effects="write", permissions=["records:write"])
def write_value() -> str:
    """Pretend to mutate an external record."""
    return "written"


if __name__ == "__main__":
    trusted = Runtime()
    assert trusted.run(write_value, {}).value == "written"

    restricted = Runtime(execution_policy=ExecutionPolicy(mode=ExecutionMode.RESTRICTED))
    assert restricted.run(read_value, {}).value == "safe"
    try:
        restricted.run(write_value, {})
    except ExecutionPolicyError as exc:
        assert exc.code == "execution_policy_violation"
        print("restricted policy rejected write")
    else:
        raise AssertionError("restricted policy should reject write-like tools")
