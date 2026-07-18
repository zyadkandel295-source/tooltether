"""Path, host, and payload safety helpers used by policy and observability."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_SECRET_KEYS = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|authorization|cookie|credential)"
)
_SECRET_VALUES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*"),
)


def redact(value: Any, secret_fields: set[str] | frozenset[str] = frozenset()) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if str(key) in secret_fields or _SECRET_KEYS.search(str(key))
            else redact(item, secret_fields)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, secret_fields) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item, secret_fields) for item in value)
    if isinstance(value, str):
        redacted = value.replace("\r", "\\r").replace("\n", "\\n")
        for pattern in _SECRET_VALUES:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value


def payload_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def normalize_resource(path: str, workspace: str | Path | None = None) -> Path:
    base = Path(workspace or Path.cwd()).resolve(strict=False)
    candidate = Path(path)
    resolved = (
        (base / candidate).resolve(strict=False)
        if not candidate.is_absolute()
        else candidate.resolve(strict=False)
    )
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Resource path escapes workspace: {path}") from exc
    return resolved


def is_public_network_target(target: str) -> bool:
    parsed = urlsplit(target if "://" in target else f"https://{target}")
    hostname = parsed.hostname
    if not hostname or hostname.lower() in {"localhost", "metadata.google.internal"}:
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return (
        not any(
            (
                address.is_private,
                address.is_loopback,
                address.is_link_local,
                address.is_multicast,
                address.is_reserved,
                address.is_unspecified,
            )
        )
        and str(address) != "169.254.169.254"
    )
