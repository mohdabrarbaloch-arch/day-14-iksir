"""Authentication endpoints: register, log in, and read the current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from ..security import PasswordError, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    try:
        password_hash = hash_password(payload.password)
    except PasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name,
        password_hash=password_hash,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email, user.role)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.access_token_minutes,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse, summary="Log in")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))

    # Verify against a dummy hash when the user is missing so that a failed
    # login takes the same time either way -- otherwise the response time tells
    # an attacker which addresses are registered.
    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token(user.id, user.email, user.role)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.access_token_minutes,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut, summary="The signed-in user")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


# A pre-computed bcrypt hash of a random string, used only to burn the same
# amount of time as a real check when the account does not exist.
_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO5YQ9Z0Yh8VY1jJ8Y5x8Yh8VY1jJ8Y5x"
