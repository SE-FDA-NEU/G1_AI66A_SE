"""Seller product creation contracts (US06, #81). Money is integer VND.

The request schema is separate from the `Product` table: the table does not validate on
construction, and the owner, code and status are set by the server, never by the client.
"""

import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from pydantic_core import PydanticCustomError

NAME_MAX_LENGTH = 200  # products.name
DESCRIPTION_MAX_LENGTH = 3000
IMAGE_URL_MAX_LENGTH = 2048
# Technical guardrails, not business rules from the issue: price x stock stays below
# JavaScript's Number.MAX_SAFE_INTEGER (2^53 - 1), so the form and cart totals never lose
# precision, and far below SQLite's 64-bit INTEGER.
PRICE_MAX = 1_000_000_000
STOCK_MAX = 1_000_000

FIELD_LABELS = {
    "name": "Product name",
    "description": "Description",
    "price": "Price",
    "stock_quantity": "Stock quantity",
    "image_url": "Image URL",
}
SERVER_OWNED_FIELDS = ("id", "code", "seller_id", "reserved_stock", "version", "is_active")
FORM_ERROR_KEY = "_form"

VALIDATION_MESSAGE = "Please correct the highlighted fields."
BODY_MESSAGE = (
    "Send the product as a JSON object with name, description, price, stock_quantity "
    "and image_url."
)
INVALID_JSON_MESSAGE = "The request body is not valid JSON."
UNKNOWN_FIELD_MESSAGE = "The request contains fields that are not accepted."
IMAGE_URL_MESSAGE = "Image URL must be an absolute http:// or https:// address."
NAME_LINE_MESSAGE = "Product name must be one line, without tabs or control characters."

# Trimming removes whitespace only. These characters also render as nothing, so text made
# of them alone (for example zero-width spaces) still counts as empty.
INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp", "Cn"})
BLANK_CHARACTERS = frozenset("ᅟᅠ⠀ㅤﾠ")  # Hangul fillers, braille blank
LINE_BREAK_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})  # newline, tab, NUL, line separators


def has_visible_character(value: str) -> bool:
    return any(
        not char.isspace()
        and char not in BLANK_CHARACTERS
        and unicodedata.category(char) not in INVISIBLE_CATEGORIES
        for char in value
    )


def vnd(amount: int) -> str:
    """Format whole VND the way the UI shows prices, e.g. `1.000.000.000 ₫`."""
    return f"{amount:,} ₫".replace(",", ".")


def is_http_url(value: str) -> bool:
    """Whether `value` is an absolute http(s) URL with a host and no whitespace."""
    if any(char.isspace() or not char.isprintable() for char in value):
        return False
    try:
        parts = urlsplit(value)
        return (
            parts.scheme.lower() in ("http", "https")
            and bool(parts.hostname)
            and (parts.port is None or parts.port > 0)
        )
    except ValueError:  # an invalid IPv6 host or an out-of-range port
        return False


class ProductCreate(BaseModel):
    """Body of `POST /api/v1/seller/products`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: StrictStr = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: StrictStr = Field(min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
    # StrictInt refuses true, 1.5, 1.0 and "100": prices are whole VND, stock is a count.
    price: StrictInt = Field(gt=0, le=PRICE_MAX)
    stock_quantity: StrictInt = Field(ge=0, le=STOCK_MAX)
    image_url: StrictStr = Field(min_length=1, max_length=IMAGE_URL_MAX_LENGTH)
    category_id: StrictInt | None = Field(default=None, ge=1)

    @field_validator("name", "description")
    @classmethod
    def visible_text(cls, value: str) -> str:
        """Refuse text that is blank once invisible characters are ignored."""
        if not has_visible_character(value):
            raise PydanticCustomError("blank_text", "The text has no visible characters.")
        return value

    @field_validator("name")
    @classmethod
    def single_line_name(cls, value: str) -> str:
        """A name is shown on one line; descriptions may keep their line breaks."""
        if any(unicodedata.category(char) in LINE_BREAK_CATEGORIES for char in value):
            raise PydanticCustomError("name_line", NAME_LINE_MESSAGE)
        return value

    @field_validator("image_url")
    @classmethod
    def absolute_http_url(cls, value: str) -> str:
        """Only the URL is checked; the image is never downloaded to decide on creation."""
        if not is_http_url(value):
            raise ValueError(IMAGE_URL_MESSAGE)
        return value


class SellerProduct(BaseModel):
    """The listing as stored, returned once it is committed."""

    id: int
    code: str
    seller_id: int
    name: str
    description: str | None = ""
    price: int
    stock_quantity: int
    reserved_stock: int
    image_url: str | None = None
    is_active: bool
    is_moderated_deactivated: bool = False
    version: int


class SellerProductResponse(BaseModel):
    data: SellerProduct


class SellerProductListResponse(BaseModel):
    data: list[SellerProduct]


def field_message(field: str, error: Mapping[str, Any]) -> str:
    """A message for one invalid product field; the submitted value is never repeated."""
    label = FIELD_LABELS[field]
    kind = error["type"]
    if kind in ("missing", "string_too_short", "blank_text") or error.get("input", "") is None:
        return f"{label} is required."
    if kind == "string_too_long":
        return f"{label} must be at most {error['ctx']['max_length']} characters."
    if kind == "name_line":
        return NAME_LINE_MESSAGE
    if field == "price":
        if kind == "greater_than":
            return "Price must be greater than 0 ₫."
        if kind == "less_than_equal":
            return f"Price must be at most {vnd(PRICE_MAX)}."
        return "Price must be a whole number of VND."
    if field == "stock_quantity":
        if kind == "greater_than_equal":
            return "Stock quantity must be 0 or more."
        if kind == "less_than_equal":
            return f"Stock quantity must be at most {STOCK_MAX:,}.".replace(",", ".")
        return "Stock quantity must be a whole number."
    if field == "image_url" and kind == "value_error":
        return IMAGE_URL_MESSAGE
    return f"{label} must be text."


def request_message(error: Mapping[str, Any]) -> str:
    """A message for an error that belongs to the whole request rather than one field."""
    loc = error.get("loc", ())
    name = loc[1] if len(loc) == 2 else None
    if error["type"] == "json_invalid":
        return INVALID_JSON_MESSAGE
    if error["type"] == "extra_forbidden":
        if name in SERVER_OWNED_FIELDS:
            return f"{name} is set by the server and cannot be sent."
        return UNKNOWN_FIELD_MESSAGE
    return BODY_MESSAGE


def validation_error_detail(errors: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Group validation errors by product field, so the form can show each one beside its input.

    Errors that are not about one product field (malformed JSON, a body that is not an
    object, fields the client may not send) are listed under `_form`.
    """
    fields: dict[str, list[str]] = {}
    for error in errors:
        loc = error.get("loc", ())
        name = loc[1] if len(loc) == 2 and loc[0] == "body" else None
        if name in FIELD_LABELS and error["type"] != "extra_forbidden":
            key, message = name, field_message(name, error)
        else:
            key, message = FORM_ERROR_KEY, request_message(error)
        messages = fields.setdefault(key, [])
        if message not in messages:
            messages.append(message)
    if any(key != FORM_ERROR_KEY for key in fields):
        message = VALIDATION_MESSAGE
    else:
        message = fields.get(FORM_ERROR_KEY, [BODY_MESSAGE])[0]
    return {"error": {"code": "ERR_VALIDATION", "message": message, "fields": fields}}
