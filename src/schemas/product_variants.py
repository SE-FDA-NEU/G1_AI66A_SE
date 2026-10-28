import re
import unicodedata
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from src.models.product_variant import ProductVariant


class VariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    sku: StrictStr = Field(min_length=1, max_length=64)
    name: StrictStr = Field(min_length=1, max_length=100)
    price: StrictInt = Field(gt=0, le=1_000_000_000)
    stock_quantity: StrictInt = Field(ge=0, le=1_000_000)
    image_url: StrictStr | None = Field(default=None, max_length=2048)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        normalized = value.upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,63}", normalized):
            raise ValueError("SKU may contain only letters, numbers, dot, underscore and hyphen.")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not any(char.isprintable() and not char.isspace() for char in value):
            raise ValueError("Variant name must contain visible text.")
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("Variant name cannot contain control characters.")
        return value

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("Image URL must be an absolute http:// or https:// address.")
        return value


class VariantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: StrictInt = Field(gt=0)
    sku: StrictStr | None = Field(default=None, min_length=1, max_length=64)
    name: StrictStr | None = Field(default=None, min_length=1, max_length=100)
    price: StrictInt | None = Field(default=None, gt=0, le=1_000_000_000)
    stock_quantity: StrictInt | None = Field(default=None, ge=0, le=1_000_000)
    image_url: StrictStr | None = Field(default=None, max_length=2048)
    is_active: bool | None = None

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return VariantCreate(sku=value, name="variant", price=1, stock_quantity=0).sku

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return VariantCreate(sku="VALID", name=value, price=1, stock_quantity=0).name

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        return VariantCreate(
            sku="VALID", name="variant", price=1, stock_quantity=0, image_url=value
        ).image_url


class VariantResponse(BaseModel):
    id: int
    product_id: int
    sku: str
    name: str
    price: int
    stock_quantity: int
    reserved_stock: int
    available_stock: int
    image_url: str | None
    is_active: bool
    version: int

    @classmethod
    def from_model(cls, variant: ProductVariant) -> "VariantResponse":
        return cls(
            id=variant.id,
            product_id=variant.product_id,
            sku=variant.sku,
            name=variant.name,
            price=variant.price,
            stock_quantity=variant.stock_quantity,
            reserved_stock=variant.reserved_stock,
            available_stock=variant.stock_quantity - variant.reserved_stock,
            image_url=variant.image_url,
            is_active=variant.is_active,
            version=variant.version,
        )


class VariantResponseEnvelope(BaseModel):
    data: VariantResponse


class VariantListResponse(BaseModel):
    data: list[VariantResponse]
