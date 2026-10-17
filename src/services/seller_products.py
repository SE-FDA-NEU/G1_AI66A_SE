"""Seller product creation (US06, BR5, BR9) on top of the `products` table.

The caller passes the request session and the authenticated seller id; this module never reads
tokens or HTTP requests. It commits or rolls back on its own, so a router must not commit again.
"""

import secrets

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.models.product import Product
from src.schemas.seller_products import ProductCreate, SellerProduct

CODE_PREFIX = "P-"
CODE_RANDOM_BYTES = 9  # 18 hex characters: with the prefix, exactly products.code's 20
MAX_CODE_ATTEMPTS = 3
CODE_CONFLICT_MESSAGE = "Could not assign a unique product code. Please submit again."


class SellerProductError(Exception):
    """A creation request that could not complete; nothing was written."""

    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def generate_product_code() -> str:
    """A random public code such as `P-6E1059D348A4CB729F`.

    Uniqueness is guaranteed by the UNIQUE constraint on `products.code`, not by the
    generator; the code is never derived from MAX(code) or the row id.
    """
    return CODE_PREFIX + secrets.token_hex(CODE_RANDOM_BYTES).upper()


def code_taken(session: Session, code: str) -> bool:
    return session.exec(select(Product.id).where(Product.code == code)).first() is not None


def create_product(session: Session, seller_id: int, data: ProductCreate) -> SellerProduct:
    """Create one active listing owned by `seller_id`, or roll all of it back.

    The owner comes from the authenticated seller (BR5); price and stock were validated by
    `ProductCreate` and are backed by the table's CHECK constraints (BR9). A new listing has
    no reserved stock, starts at version 1 and is active even when its stock is 0.

    Only a confirmed product-code collision runs the insert again with a new code, at most
    MAX_CODE_ATTEMPTS times. Any other failure is rolled back and raised unchanged.
    """
    for _attempt in range(MAX_CODE_ATTEMPTS):
        code = generate_product_code()
        product = Product(
            code=code,
            seller_id=seller_id,
            **data.model_dump(),
            reserved_stock=0,
            version=1,
            is_active=True,
        )
        try:
            session.add(product)
            session.flush()
            # Built before commit: committing expires the row and would reload it.
            created = SellerProduct.model_validate(product, from_attributes=True)
            session.commit()
            return created
        except IntegrityError:
            session.rollback()
            if not code_taken(session, code):
                raise
        except Exception:
            session.rollback()
            raise
    raise SellerProductError("ERR_CONCURRENCY_CONFLICT", CODE_CONFLICT_MESSAGE)
