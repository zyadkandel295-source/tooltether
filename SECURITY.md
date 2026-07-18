# Security policy

This pre-publication alpha has no public security mailbox yet. Before publication, add a monitored private contact address and enable private vulnerability reporting in GitHub.

Do not disclose suspected credential leakage, policy bypass, cross-tenant cache access, unsafe retry, path traversal, SSRF, plugin execution, or audit-integrity defects in a public issue. Include affected version, minimal reproduction, impact, and proposed embargo window.

ToolTether does not sandbox Python handlers. Reports whose only premise is that directly invoked arbitrary Python can access its process are outside the intended boundary unless a documented runtime control is bypassed.
