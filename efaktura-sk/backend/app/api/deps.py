from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Membership, Role, User
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_db)]

WRITE_ROLES = {Role.OWNER, Role.ACCOUNTANT, Role.MEMBER}
ADMIN_ROLES = {Role.OWNER, Role.ACCOUNTANT}


def current_user(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    user_id = decode_token(creds.credentials) if creds else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Prihláste sa, prosím.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def membership(db: Session, user: User, company_id: int) -> Membership:
    m = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.company_id == company_id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Firma neexistuje alebo k nej nemáte prístup.")
    return m


def company_for(db: Session, user: User, company_id: int, roles: set[str] | None = None) -> Company:
    m = membership(db, user, company_id)
    if roles and m.role not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Na túto akciu nemáte oprávnenie.")
    return m.company
