from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from app.api.dependencies import AUTH_COOKIE, get_current_user, get_db
from app.core.audit import audit, mask_email
from app.core.config import settings
from app.core.rate_limit import limiter, rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

# Verified against when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("not-a-real-password")


def _set_session_cookie(response: Response, user_id: str, remember: bool = True) -> str:
    token = create_access_token(user_id)
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=settings.AUTH_TOKEN_TTL_MINUTES * 60 if remember else None,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return token


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", 10, 3600))],
)
def register(req: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Creates an operator account and signs it in."""
    if not settings.registration_open:
        audit("register_blocked", request, email=mask_email(req.email))
        raise HTTPException(status_code=403, detail="Self-registration is disabled in this environment")
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(name=req.name, email=req.email, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    audit("register", request, user=user.id, email=mask_email(user.email))
    return TokenResponse(access_token=_set_session_cookie(response, user.id), user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit("login", 20, 60))])
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    # Per-account cap stops distributed guessing against one email; PBKDF2 makes each attempt expensive.
    try:
        limiter.check(f"login-email:{email}", 8, 300)
    except HTTPException:
        audit("login_locked", request, email=mask_email(email))
        raise
    user = db.query(User).filter(User.email == email).first()
    ok = verify_password(req.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        audit("login_failed", request, email=mask_email(email))
        raise HTTPException(status_code=401, detail="Your email or password is incorrect. Please try again.")
    audit("login", request, user=user.id)
    return TokenResponse(
        access_token=_set_session_cookie(response, user.id, req.remember), user=UserResponse.model_validate(user)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    """Clears the session cookie."""
    audit("logout", request)
    response.delete_cookie(
        AUTH_COOKIE,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)
