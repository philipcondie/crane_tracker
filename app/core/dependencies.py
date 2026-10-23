from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models.base import AdminUser
from app.services.auth import get_admin

SessionDep = Annotated[Session, Depends(get_session)]


bearer = HTTPBearer(auto_error=False)
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def require_admin(session: SessionDep, credentials: BearerDep) -> AdminUser:
    user = get_admin(session, credentials.credentials) if credentials else None
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Valid admin token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


AdminDep = Annotated[AdminUser, Depends(require_admin)]
