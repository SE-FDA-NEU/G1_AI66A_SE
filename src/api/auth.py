"""Authentication endpoints."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import select

from src.auth import CurrentUser, create_access_token, verify_password
from src.config import get_settings
from src.database import SessionDep
from src.errors import error_detail
from src.models.user import User
from src.services.google_signin import GoogleSignInError, sign_in_with_google

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("email must be valid")
        return value.lower()


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=8192)


@router.get("/google/config")
def google_config() -> dict[str, str]:
    """Expose only the public OAuth web client identifier."""
    return {"client_id": get_settings().GOOGLE_CLIENT_ID}


@router.post("/google", response_model=LoginResponse)
def google_login(request: GoogleLoginRequest, session: SessionDep) -> LoginResponse:
    try:
        user = sign_in_with_google(session, request.credential, get_settings().GOOGLE_CLIENT_ID)
    except GoogleSignInError as exc:
        errors = {
            "disabled": (503, "ERR_GOOGLE_DISABLED", "Google sign-in is not configured."),
            "unavailable": (
                503,
                "ERR_GOOGLE_UNAVAILABLE",
                "Google sign-in is unavailable. Try again.",
            ),
            "invalid": (401, "ERR_GOOGLE_INVALID", "Google sign-in could not be verified."),
            "restricted": (403, "ERR_ACCOUNT_RESTRICTED", "This account is restricted."),
            "email_conflict": (
                409,
                "ERR_EMAIL_IN_USE",
                "An account already uses this email. Sign in with your existing method.",
            ),
            "conflict": (
                409,
                "ERR_GOOGLE_CONFLICT",
                "Sign-in could not be completed. Please retry.",
            ),
        }
        code, error_code, message = errors[exc.code]
        raise HTTPException(status_code=code, detail=error_detail(error_code, message)) from None
    return LoginResponse(
        access_token=create_access_token(user),
        user=UserResponse.model_validate(user, from_attributes=True),
    )


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, session: SessionDep) -> LoginResponse:
    """Authenticate a user and issue a signed bearer token."""
    user = session.exec(select(User).where(User.email == request.email)).first()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("ERR_INVALID_CREDENTIALS", "Email or password is incorrect."),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return LoginResponse(
        access_token=create_access_token(user),
        user=UserResponse.model_validate(user, from_attributes=True),
    )


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    """Return the identity represented by the current bearer token."""
    return UserResponse.model_validate(user, from_attributes=True)
