"""Common API error responses."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiError:
    """Stable error code/message pair returned by the API."""

    code: str
    message: str


def error_detail(code: str, message: str) -> dict[str, dict[str, str]]:
    """Build the common API error envelope."""
    return {"error": {"code": code, "message": message}}
