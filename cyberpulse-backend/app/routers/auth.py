import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import OAuthState, User, utcnow
from ..schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut, UserUpdate
from ..security import create_access_token, decode_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


# ── Email + password ──────────────────────────────────────────────────────
@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(
        name=payload.name.strip(),
        email=email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        provider="password",
        last_active=utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    user.last_active = utcnow()
    db.commit()
    db.refresh(user)
    return _auth_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(
    updates: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.post("/logout")
def logout(_: User = Depends(get_current_user)):
    # JWTs are stateless; the client drops the token. Endpoint exists so the
    # frontend has a single place to hook future token revocation.
    return {"success": True}


# ── OAuth helpers ─────────────────────────────────────────────────────────
def _new_state(db: Session, provider: str, user_id: int | None = None) -> str:
    state = secrets.token_urlsafe(24)
    db.add(OAuthState(state=state, provider=provider, user_id=user_id))
    db.commit()
    return state


def _consume_state(db: Session, state: str, provider: str) -> OAuthState | None:
    row = db.get(OAuthState, state or "")
    if row is None or row.provider != provider:
        return None
    db.delete(row)
    db.commit()
    return row


def _fe(path: str, **params) -> RedirectResponse:
    url = f"{settings.frontend_url}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    return RedirectResponse(url)


# ── Google sign-in ────────────────────────────────────────────────────────
@router.get("/google")
def google_start(db: Session = Depends(get_db)):
    if not settings.google_client_id or not settings.google_client_secret:
        return _fe("/auth-callback", error="config")

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": f"{settings.backend_url}/api/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": _new_state(db, "google"),
        "prompt": "select_account",
    }
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        return _fe("/auth-callback", error="access_denied")
    if not _consume_state(db, state or "", "google"):
        return _fe("/auth-callback", error="state_mismatch")
    if not code:
        return _fe("/auth-callback", error="no_code")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_res = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": f"{settings.backend_url}/api/auth/google/callback",
                    "grant_type": "authorization_code",
                },
            )
            if token_res.status_code != 200:
                return _fe("/auth-callback", error="invalid_token")

            access_token = token_res.json().get("access_token")
            if not access_token:
                return _fe("/auth-callback", error="no_id_token")

            profile_res = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if profile_res.status_code != 200:
                return _fe("/auth-callback", error="invalid_token")
            profile = profile_res.json()
    except httpx.HTTPError:
        return _fe("/auth-callback", error="server_error")

    if not profile.get("email_verified", False):
        return _fe("/auth-callback", error="email_not_verified")

    email = (profile.get("email") or "").lower()
    if not email:
        return _fe("/auth-callback", error="invalid_token")

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            name=profile.get("name") or email.split("@")[0],
            email=email,
            role="Student",
            provider="google",
            picture=profile.get("picture"),
        )
        db.add(user)
    else:
        user.picture = profile.get("picture") or user.picture
        user.provider = user.provider or "google"

    user.last_active = utcnow()
    db.commit()
    db.refresh(user)

    return _fe("/auth-callback", token=create_access_token(user.id))


# ── GitHub portfolio connect ──────────────────────────────────────────────
@router.get("/github")
def github_start(token: str = Query(...), db: Session = Depends(get_db)):
    user_id = decode_token(token)
    if user_id is None:
        return _fe("/dashboard/settings", github="invalid_token")
    if not settings.github_client_id or not settings.github_client_secret:
        return _fe("/dashboard/settings", github="config")

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.backend_url}/api/auth/github/callback",
        "scope": "read:user public_repo",
        "state": _new_state(db, "github", user_id),
    }
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{urlencode(params)}")


@router.get("/github/callback")
async def github_callback(
    code: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    row = _consume_state(db, state or "", "github")
    if row is None:
        return _fe("/dashboard/settings", github="state_mismatch")
    if not code:
        return _fe("/dashboard/settings", github="no_code")

    user = db.get(User, row.user_id) if row.user_id else None
    if user is None:
        return _fe("/dashboard/settings", github="invalid_token")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_res = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": f"{settings.backend_url}/api/auth/github/callback",
                },
            )
            gh_token = token_res.json().get("access_token") if token_res.status_code == 200 else None
            if not gh_token:
                return _fe("/dashboard/settings", github="invalid_token")

            profile_res = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
            )
            if profile_res.status_code != 200:
                return _fe("/dashboard/settings", github="invalid_token")
            profile = profile_res.json()
    except httpx.HTTPError:
        return _fe("/dashboard/settings", github="server_error")

    user.github_connected = True
    user.github_username = profile.get("login")
    user.github_token = gh_token
    db.commit()

    return _fe("/dashboard/settings", github="connected")


@router.post("/github/disconnect", response_model=UserOut)
def github_disconnect(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.github_connected = False
    user.github_username = None
    user.github_token = None
    db.commit()
    db.refresh(user)
    return user
