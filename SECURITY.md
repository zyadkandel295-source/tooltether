# Security policy

Report security issues privately through GitHub Security Advisories / private vulnerability reporting for this repository. If that channel is unavailable, contact the repository owner before opening a public issue.

Do not disclose suspected credential leakage, policy bypass, cross-tenant cache access, unsafe retry, path traversal, SSRF, plugin execution, or audit-integrity defects in a public issue. Include affected version, minimal reproduction, impact, and proposed embargo window.

ToolTether does not sandbox Python handlers. Reports whose only premise is that directly invoked arbitrary Python can access its process are outside the intended boundary unless a documented runtime control is bypassed.
