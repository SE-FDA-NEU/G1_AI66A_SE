"""Verify Google credentials and create an isolated buyer identity."""

from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from src.models.user import User
from src.repositories.google_identity import GoogleIdentityRepository


class GoogleSignInError(Exception):
    def __init__(self, code: str):
        self.code = code


def verify_google_credential(credential: str, client_id: str) -> dict:
    try:
        return id_token.verify_oauth2_token(credential, Request(), client_id)
    except TransportError as exc:
        raise GoogleSignInError("unavailable") from exc
    except (ValueError, GoogleAuthError, KeyError) as exc:
        raise GoogleSignInError("invalid") from exc


def sign_in_with_google(session: Session, credential: str, client_id: str) -> User:
    if not client_id:
        raise GoogleSignInError("disabled")
    claims = verify_google_credential(credential, client_id)
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise GoogleSignInError("invalid")
    repository = GoogleIdentityRepository(session)
    user = repository.find_user(subject)
    if user:
        if user.status != "ACTIVE":
            raise GoogleSignInError("restricted")
        return user
    email = claims.get("email")
    if (
        claims.get("email_verified") is not True
        or not isinstance(email, str)
        or not email
        or len(email) > 255
        or "@" not in email
    ):
        raise GoogleSignInError("invalid")
    email = email.lower()
    if repository.email_exists(email):
        raise GoogleSignInError("email_conflict")
    name = claims.get("name")
    name = name.strip()[:100] if isinstance(name, str) and name.strip() else email[:100]
    try:
        user = repository.add_buyer(subject, email, name)
        session.commit()
        session.refresh(user)
        return user
    except IntegrityError as exc:
        session.rollback()
        raise GoogleSignInError("conflict") from exc
