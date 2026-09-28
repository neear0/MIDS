from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app import audit
from app.api.deps import DB, CurrentUser
from app.api.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.models import User
from app.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: DB) -> TokenOut:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Účet s týmto e-mailom už existuje.")
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name)
    db.add(user)
    db.flush()
    audit.record(db, action="user.registered", user_id=user.id, entity_type="user", entity_id=user.id)
    db.commit()
    return TokenOut(access_token=create_token(user.id))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DB) -> TokenOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nesprávny e-mail alebo heslo.")
    return TokenOut(access_token=create_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name)
