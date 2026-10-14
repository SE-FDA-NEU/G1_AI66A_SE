import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session

from src.auth import SellerUser, create_access_token, decode_access_token, hash_password
from src.database import engine
from src.main import create_app
from src.models.user import User
from src.seed import (
    DEFAULT_DEV_PASSWORD,
    DEMO_BUYER_EMAIL,
    DEMO_SELLER_EMAIL,
    seed_users,
)


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


@pytest.mark.parametrize(
    "malformed_token",
    [
        "not-a-token",
        "header.payload",
        "header.payload.signature.extra",
        "invalid!@#.invalid!@#.invalid!@#",
        "!!!.@@@.###",
        "...",
        "==.==.==",
        "bad_base64.bad_payload.bad_signature",
    ],
)
def test_malformed_bearer_tokens_return_401_not_500(
    client: TestClient,
    malformed_token: str,
) -> None:
    """A completely malformed JWT must consistently return 401 ERR_INVALID_TOKEN, never 500."""
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {malformed_token}"},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "ERR_INVALID_TOKEN",
            "message": "The access token is invalid or expired.",
        }
    }

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(malformed_token)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["error"]["code"] == "ERR_INVALID_TOKEN"


def test_seeded_credentials_login_flow(client: TestClient) -> None:
    """Verify reproducible fresh-machine login flow using standard seeded credentials."""
    with Session(engine) as session:
        seed_users(session)
        session.commit()

    # Verify seller login
    seller_response = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_SELLER_EMAIL, "password": DEFAULT_DEV_PASSWORD},
    )
    assert seller_response.status_code == 200
    seller_body = seller_response.json()
    assert seller_body["user"]["role"] == "seller"
    assert seller_body["user"]["email"] == DEMO_SELLER_EMAIL
    assert "password" not in seller_body["user"]

    seller_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {seller_body['access_token']}"},
    )
    assert seller_me.status_code == 200
    assert seller_me.json()["role"] == "seller"

    # Verify buyer login with PR test credentials (user@example.com / password)
    buyer_response = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_BUYER_EMAIL, "password": DEFAULT_DEV_PASSWORD},
    )
    assert buyer_response.status_code == 200
    buyer_body = buyer_response.json()
    assert buyer_body["user"]["role"] == "buyer"
    assert buyer_body["user"]["email"] == DEMO_BUYER_EMAIL

    buyer_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {buyer_body['access_token']}"},
    )
    assert buyer_me.status_code == 200
    assert buyer_me.json()["role"] == "buyer"

    # Verify invalid password on seeded user
    invalid_login = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_BUYER_EMAIL, "password": "wrong-password"},
    )
    assert invalid_login.status_code == 401
    assert invalid_login.json()["error"]["code"] == "ERR_INVALID_CREDENTIALS"
