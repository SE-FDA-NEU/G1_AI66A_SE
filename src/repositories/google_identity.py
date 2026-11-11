from sqlalchemy import func
from sqlmodel import Session, select

from src.models.google_identity import GoogleIdentity
from src.models.user import User


class GoogleIdentityRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_user(self, subject: str) -> User | None:
        identity = self.session.get(GoogleIdentity, subject)
        return self.session.get(User, identity.user_id) if identity else None

    def email_exists(self, email: str) -> bool:
        return (
            self.session.exec(select(User.id).where(func.lower(User.email) == email)).first()
            is not None
        )

    def add_buyer(self, subject: str, email: str, name: str) -> User:
        # An explicit unusable hash also prevents the demo seed from assigning
        # a default password to a Google-only account with a matching email.
        user = User(email=email, name=name, role="buyer", password_hash="!google-only")
        self.session.add(user)
        self.session.flush()
        self.session.add(GoogleIdentity(subject=subject, user_id=user.id))
        return user
