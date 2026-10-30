"""Shared phone and visible-text validation for delivery contracts."""

import re
import unicodedata


def valid_phone(value: str) -> str:
    normalized = re.sub(r" {2,}", " ", value.strip())
    if any(c not in "+0123456789 ()-" for c in normalized):
        raise ValueError("Phone contains invalid characters")
    if not 7 <= sum(c in "0123456789" for c in normalized) <= 15:
        raise ValueError("Phone must contain 7 to 15 digits")
    return normalized


def visible_text(value: str) -> str:
    if not any(not c.isspace() and not unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("Enter text with visible characters.")
    return value
