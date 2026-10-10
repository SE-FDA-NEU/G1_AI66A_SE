"""Tests for authentication and role authorization."""

from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlmodel import Session

from src.auth import SellerUser, create_access_token, hash_password
from src.database import engine
from src.main import create_app
from src.models.user import User


def add_user(user_id: int, role: str, password: str = "correct-password") -> User:
    user = User(
        id=user_id,
        name=f"Test {role}",
        email=f"{role}{user_id}@marketplace.local",
        password_hash=hash_password(password),
        role=role,
    )
    with Session(engine, expire_on_commit=False) as session:
        session.add(user)
        session.commit()
    return user


def test_login_and_me_return_user_without_password(client: TestClient) -> None:
    user = add_user(10, "buyer")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"] == {
        "id": 10,
        "name": "Test buyer",
        "email": user.email,
        "role": "buyer",
    }
    assert "password" not in body["user"]

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["id"] == 10


def test_invalid_credentials_use_common_error_shape(client: TestClient) -> None:
    user = add_user(11, "buyer")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ERR_INVALID_CREDENTIALS"


def test_missing_and_expired_tokens_are_rejected(client: TestClient) -> None:
    user = add_user(12, "buyer")

    missing = client.get("/api/v1/auth/me")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "ERR_AUTH_REQUIRED"

    expired_token = create_access_token(user, expires_in=-1)
    expired = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "ERR_INVALID_TOKEN"


def test_role_mismatch_in_token_is_rejected(client: TestClient) -> None:
    user = add_user(13, "buyer")
    token = create_access_token(user)
    parts = token.split(".")
    # Keep the signature from the buyer token but change the role claim.
    # Signature validation must reject this tampering before role checks run.
    import base64
    import json

    payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
    payload["role"] = "seller"
    parts[1] = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {'.'.join(parts)}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ERR_INVALID_TOKEN"


def test_buyer_cannot_use_seller_dependency(client: TestClient) -> None:
    user = add_user(14, "buyer")
    token = create_access_token(user)

    router = APIRouter(prefix="/test-seller")

    @router.get("")
    def seller_only(current_user: SellerUser) -> dict[str, str]:
        del current_user
        return {"status": "ok"}

    test_app = create_app()
    test_app.include_router(router)
    with TestClient(test_app) as test_client:
        response = test_client.get(
            "/test-seller",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ERR_SELLER_REQUIRED"
