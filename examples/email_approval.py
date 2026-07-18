from tooltether import NonInteractiveApprovalHandler, Runtime, tool


@tool(
    side_effects="external",
    permissions=["communication:send"],
    approval_required=True,
    idempotent=True,
)
def fake_send_email(subject: str) -> str:
    """Send through a local fake transport."""
    return f"fake-sent:{subject}"


if __name__ == "__main__":
    runtime = Runtime(approval_handler=NonInteractiveApprovalHandler(allow=True))
    print(runtime.run(fake_send_email, {"subject": "weekly"}, idempotency_key="week-1").value)
