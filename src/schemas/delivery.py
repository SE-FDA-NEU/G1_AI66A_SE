"""Shared phone and visible-text validation for delivery contracts."""

import re
import unicodedata


def normalize_phone(value: str) -> str:
    return re.sub(r" {2,}", " ", value.strip())


def valid_phone(value: str) -> str:
    cleaned = value.strip()
    if any(c not in "+0123456789 ()-" for c in cleaned):
        raise ValueError("Phone contains invalid characters")
    if not 7 <= sum(c in "0123456789" for c in cleaned) <= 15:
        raise ValueError("Phone must contain 7 to 15 digits")
    return value


def visible_text(value: str) -> str:
    if not any(not c.isspace() and not unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("Enter text with visible characters.")
    return value
