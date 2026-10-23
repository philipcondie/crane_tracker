from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, SecretStr

from app.core.config import get_settings
from app.core.dependencies import AdminDep, BearerDep, SessionDep
from app.core.limiter import limiter
from app.services import auth

router = APIRouter(prefix="/admin", tags=["admin"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: SecretStr = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=TokenResponse)
@limiter.limit(get_settings().admin_login_rate_limit)
def login(
    request: Request, response: Response, session: SessionDep, body: LoginRequest
):
    token = auth.sign_in(
        session, username=body.username, password=body.password.get_secret_value()
    )
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    session.commit()
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=token, expires_in=get_settings().admin_token_ttl_seconds
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: SessionDep, admin: AdminDep, credentials: BearerDep):
    auth.sign_out(session, credentials.credentials)
    session.commit()
