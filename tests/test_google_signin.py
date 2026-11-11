"""Google credential exchange keeps provider identity and app roles separate."""

import os
import sqlite3
import subprocess
import sys
import time

import pytest
import rsa
from google.auth import crypt, jwt
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.auth import hash_password
from src.config import get_settings
from src.database import engine
from src.models.google_identity import GoogleIdentity
from src.models.user import User
from src.services import google_signin


@pytest.fixture
def google_enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "GOOGLE_CLIENT_ID", "test.apps.googleusercontent.com")
    claims = {
        "sub": "subject-1",
        "email": "new-google@example.com",
        "email_verified": True,
        "name": "Google Buyer",
    }
    monkeypatch.setattr(google_signin, "verify_google_credential", lambda token, audience: claims)
    return claims


def test_google_creates_buyer_and_reuses_subject_even_if_email_changes(client, google_enabled):
    first = client.post("/api/v1/auth/google", json={"credential": "verified-token"})
    assert first.status_code == 200
    body = first.json()
    assert body["user"]["role"] == "buyer"
    with Session(engine) as session:
        assert session.get(User, body["user"]["id"]).password_hash == "!google-only"
    assert client.post(
        "/api/v1/auth/login", json={"email": "new-google@example.com", "password": "password"}
    ).status_code == 401
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer " + body["access_token"]}
        ).status_code
        == 200
    )
    denied = client.get(
        "/api/v1/seller/inventory", headers={"Authorization": "Bearer " + body["access_token"]}
    )
    assert denied.status_code == 403
    google_enabled["email"] = "changed@example.com"
    second = client.post("/api/v1/auth/google", json={"credential": "verified-token"})
    assert second.status_code == 200
    assert second.json()["user"]["id"] == body["user"]["id"]


def test_existing_email_is_not_automatically_linked_or_given_seller_role(client, google_enabled):
    with Session(engine) as session:
        session.add(
            User(
                name="Seller",
                email="Seller-Google@example.com",
                role="seller",
                password_hash=hash_password("password"),
            )
        )
        session.commit()
    google_enabled.update(sub="subject-collision", email="seller-google@example.com")
    response = client.post("/api/v1/auth/google", json={"credential": "token"})
    assert response.status_code == 409
    with Session(engine) as session:
        assert session.get(GoogleIdentity, "subject-collision") is None
        user = session.exec(select(User).where(User.email == "Seller-Google@example.com")).one()
        assert user.role == "seller"


@pytest.mark.parametrize("field,value", [("email_verified", False), ("sub", ""), ("email", "bad")])
def test_invalid_claims_are_rejected_without_account_creation(client, google_enabled, field, value):
    google_enabled.update(sub="invalid-claim", email="invalid-claim@example.com")
    google_enabled[field] = value
    response = client.post("/api/v1/auth/google", json={"credential": "token"})
    assert response.status_code == 401
    with Session(engine) as session:
        assert session.get(GoogleIdentity, "invalid-claim") is None
        assert (
            session.exec(select(User).where(User.email == "invalid-claim@example.com")).first()
            is None
        )


def test_restricted_linked_user_cannot_sign_in(client, google_enabled):
    google_enabled.update(sub="restricted-sub", email="restricted-google@example.com")
    first = client.post("/api/v1/auth/google", json={"credential": "token"})
    with Session(engine) as session:
        user = session.get(User, first.json()["user"]["id"])
        user.status = "SUSPENDED"
        session.add(user)
        session.commit()
    assert client.post("/api/v1/auth/google", json={"credential": "token"}).status_code == 403


def test_disabled_and_invalid_google_credentials_fail_closed(client, monkeypatch, google_enabled):
    monkeypatch.setattr(get_settings(), "GOOGLE_CLIENT_ID", "")
    assert client.post("/api/v1/auth/google", json={"credential": "token"}).status_code == 503
    monkeypatch.setattr(get_settings(), "GOOGLE_CLIENT_ID", "test.apps.googleusercontent.com")

    def reject(token, audience):
        raise google_signin.GoogleSignInError("invalid")

    monkeypatch.setattr(google_signin, "verify_google_credential", reject)
    assert client.post("/api/v1/auth/google", json={"credential": "bad"}).status_code == 401


def test_google_verifier_checks_signature_audience_issuer_and_expiry(monkeypatch):
    public_key, private_key = rsa.newkeys(1024)
    signer = crypt.RSASigner.from_string(private_key.save_pkcs1(), key_id="test-key")
    monkeypatch.setattr(
        google_signin.id_token,
        "_fetch_certs",
        lambda request, url: {"test-key": public_key.save_pkcs1().decode()},
    )
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "client-id",
        "sub": "123",
        "iat": now,
        "exp": now + 60,
    }
    token = jwt.encode(signer, claims).decode()
    assert google_signin.verify_google_credential(token, "client-id")["sub"] == "123"
    with pytest.raises(google_signin.GoogleSignInError):
        google_signin.verify_google_credential(token, "wrong-client")
    for changes in ({"iss": "https://evil.example"}, {"exp": now - 60}):
        invalid = jwt.encode(signer, {**claims, **changes}).decode()
        with pytest.raises(google_signin.GoogleSignInError):
            google_signin.verify_google_credential(invalid, "client-id")
    other_signer = crypt.RSASigner.from_string(rsa.newkeys(1024)[1].save_pkcs1(), key_id="test-key")
    forged = jwt.encode(other_signer, claims).decode()
    with pytest.raises(google_signin.GoogleSignInError):
        google_signin.verify_google_credential(forged, "client-id")


def test_failed_identity_insert_rolls_back_new_user(client, google_enabled, monkeypatch):
    google_enabled.update(sub="rollback-sub", email="rollback-google@example.com")

    def fail_after_user_insert(repository, subject, email, name):
        repository.session.add(User(name=name, email=email, role="buyer"))
        repository.session.flush()
        raise IntegrityError("insert", {}, Exception("injected failure"))

    monkeypatch.setattr(google_signin.GoogleIdentityRepository, "add_buyer", fail_after_user_insert)
    assert client.post("/api/v1/auth/google", json={"credential": "token"}).status_code == 409
    with Session(engine) as session:
        assert (
            session.exec(select(User).where(User.email == "rollback-google@example.com")).first()
            is None
        )
        assert session.get(GoogleIdentity, "rollback-sub") is None


def test_initialization_preserves_legacy_users_and_creates_google_identity_table(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(100), "
            "email VARCHAR(255), role VARCHAR(20))"
        )
        connection.execute(
            "INSERT INTO users (id, name, email, role) VALUES "
            "(1, 'Existing', 'old@example.com', 'seller')"
        )
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database}", "DEBUG": "false"}
    for _ in range(2):
        subprocess.run(
            [sys.executable, "-m", "src.database"], env=env, check=True, capture_output=True
        )
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT email, role FROM users WHERE id = 1").fetchone() == (
            "old@example.com",
            "seller",
        )
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='google_identities'"
        ).fetchone()
