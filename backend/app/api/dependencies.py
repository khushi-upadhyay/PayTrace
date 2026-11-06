from typing import Optional
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models.user import User
from app.core.audit import audit
from app.core.config import settings
from app.core.security import decode_access_token, verify_checkout_token

_bearer = HTTPBearer(auto_error=False)


AUTH_COOKIE = "paytrace_session"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "PayTrace"


def _credentials(request: Request, creds: Optional[HTTPAuthorizationCredentials]):
    """Returns (token, csrf_ok). Cookie sessions need a custom header on unsafe methods, which cross-site forms cannot send."""
    if creds:
        return creds.credentials, True
    token = request.cookies.get(AUTH_COOKIE)
    csrf_ok = request.method in _SAFE_METHODS or request.headers.get(CSRF_HEADER) == CSRF_VALUE
    return token, csrf_ok


def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolves the logged-in operator from the session cookie or an `Authorization: Bearer` header."""
    token, csrf_ok = _credentials(request, creds)
    if token and not csrf_ok:
        audit("csrf_rejected", request, path=request.url.path)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing CSRF header")
    user_id = decode_access_token(token) if token else None
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not user:
        if token:
            audit("invalid_session_token", request, path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_order_access(
    order_id: str,
    request: Request,
    x_checkout_token: Optional[str] = Header(default=None),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> None:
    """Public checkout routes are keyed by order id, so require the buyer's checkout token or an operator login."""
    if verify_checkout_token(order_id, x_checkout_token):
        return
    token, csrf_ok = _credentials(request, creds)
    user_id = decode_access_token(token) if token and csrf_ok else None
    if user_id and db.query(User).filter(User.id == user_id).first():
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Checkout token required for this order")


__all__ = ["get_db", "get_current_user", "require_order_access"]
