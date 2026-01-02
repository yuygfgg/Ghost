from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from packages.core.auth import Principal, Role, verify_token
from packages.db import SessionLocal


def get_db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_principal(
    authorization: str = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_db),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    token = authorization.split(" ", 1)[1].strip()
    principal = verify_token(session, token)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return principal


def require_roles(*roles: Role):
    def wrapper(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
            )
        return principal

    return wrapper
