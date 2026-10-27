"""Address mutations are atomic, owner-scoped, versioned and bounded on contention."""

import time
from datetime import UTC, datetime

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select

from src.models.user_address import UserAddress
from src.schemas.addresses import AddressCreate, AddressData, AddressUpdate


class AddressError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def owned_address(
    session: Session, user_id: int, address_id: int, version: int | None = None
) -> UserAddress:
    row = session.exec(
        select(UserAddress)
        .where(UserAddress.id == address_id, UserAddress.user_id == user_id)
        .execution_options(populate_existing=True)
    ).first()
    if row is None:
        raise AddressError(
            "ERR_ADDRESS_NOT_FOUND", "Address not found. Reload your address book.", 404
        )
    if version is not None and row.version != version:
        raise AddressError("ERR_ADDRESS_CHANGED", "Address changed. Review it before continuing.")
    return row


def list_addresses(session: Session, user_id: int) -> list[AddressData]:
    return [
        AddressData.model_validate(row)
        for row in session.exec(
            select(UserAddress)
            .where(UserAddress.user_id == user_id)
            .order_by(UserAddress.is_default.desc(), UserAddress.id)
        ).all()
    ]


def mutate_address(
    session: Session,
    user_id: int,
    action: str,
    body: AddressCreate | AddressUpdate | None = None,
    address_id: int | None = None,
    version: int | None = None,
) -> AddressData | None:
    for attempt in range(5):
        try:
            now = datetime.now(UTC)
            values = body.model_dump(exclude={"version"}) if body else {}
            if action == "create":
                first = (
                    session.exec(
                        select(UserAddress.id).where(UserAddress.user_id == user_id)
                    ).first()
                    is None
                )
                values["is_default"] = first or values["is_default"]
            else:
                owned_address(session, user_id, address_id, version)
            if action == "default" or values.get("is_default"):
                session.exec(
                    update(UserAddress)
                    .where(
                        UserAddress.user_id == user_id,
                        UserAddress.id != address_id,
                        UserAddress.is_default.is_(True),
                    )
                    .values(is_default=False, version=UserAddress.version + 1, updated_at=now)
                    .execution_options(synchronize_session=False)
                )
                session.flush()
            if action == "create":
                row = UserAddress(user_id=user_id, **values)
                session.add(row)
                session.flush()
                address_id = row.id
            else:
                predicate = (UserAddress.id == address_id, UserAddress.user_id == user_id)
                if action == "delete":
                    statement = delete(UserAddress).where(*predicate)
                else:
                    statement = (
                        update(UserAddress)
                        .where(*predicate, UserAddress.version == version)
                        .values(
                            **(dict(is_default=True) if action == "default" else values),
                            version=UserAddress.version + 1,
                            updated_at=now,
                        )
                    )
                changed = session.exec(statement.execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise AddressError(
                        "ERR_ADDRESS_CHANGED", "Address changed. Reload and try again."
                    )
            result = (
                None
                if action == "delete"
                else AddressData.model_validate(owned_address(session, user_id, address_id))
            )
            session.commit()
            return result
        except (IntegrityError, OperationalError) as exc:
            session.rollback()
            busy = (getattr(exc.orig, "sqlite_errorcode", 0) or 0) & 255 in (5, 6)
            default_collision = isinstance(exc, IntegrityError) and (
                "UNIQUE constraint failed: user_addresses.user_id" in str(exc.orig)
                or "ux_user_addresses_one_default" in str(exc.orig)
            )
            if not busy and not default_collision:
                raise
            if attempt == 4:
                raise AddressError(
                    "ERR_CONCURRENCY_CONFLICT", "Addresses changed. Reload and retry."
                ) from exc
            time.sleep(0.01 * (attempt + 1))
        except Exception:
            session.rollback()
            raise
    raise AssertionError("unreachable")
