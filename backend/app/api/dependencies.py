from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models.user import User
from app.core.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolves the logged-in operator from the `Authorization: Bearer` header."""
    user_id = decode_access_token(creds.credentials) if creds else None
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


__all__ = ["get_db", "get_current_user"]
