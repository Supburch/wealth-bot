"""Redaction helpers for keeping sensitive identifiers out of operational logs."""

import hashlib


def mask_id(value: object) -> str:
    """Return a stable, truncated hash for safe log correlation.

    The full identifier is never returned. A short leading prefix plus a
    truncated SHA-256 digest keeps logs correlatable without exposing user
    or spreadsheet identifiers.
    """
    if value is None:
        return "<none>"
    text = str(value)
    if not text:
        return "<empty>"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"{text[:4]}…{digest}"
