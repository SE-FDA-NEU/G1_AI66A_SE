"""Shared phone and visible-text validation without changing legacy normalization."""

import unicodedata


def valid_phone(value: str) -> str:
    if any(c not in "+0123456789 ()-" for c in value):
        raise ValueError("Phone contains invalid characters")
    if not 7 <= sum(c.isdigit() for c in value) <= 15:
        raise ValueError("Phone must contain 7 to 15 digits")
    return value


def visible_text(value: str) -> str:
    if not any(not c.isspace() and not unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("Enter text with visible characters.")
    return value
