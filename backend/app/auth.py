"""Authentication & RBAC. dev mode = no login; cognito mode = verify Cognito ID token (JWT)."""
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Org, User

ROLE_LEVEL = {"viewer": 0, "analyst": 1, "admin": 2}


@dataclass
class Principal:
    user_id: str
    org_id: str
    role: str
    email: str


def _issuer() -> str:
    return f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}"


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{_issuer()}/.well-known/jwks.json")


def _upsert(db: Session, sub: str, email: str, org_key: str, org_name: str, role: str) -> Principal:
    org = db.scalar(select(Org).where(Org.slug == org_key))
    if not org:
        org = Org(name=org_name, slug=org_key)
        db.add(org)
        db.flush()
    user = db.scalar(select(User).where(User.sub == sub))
    if not user:
        user = User(sub=sub, email=email, role=role, org_id=org.id)
        db.add(user)
    else:
        user.role, user.email = role, email
    db.commit()
    return Principal(user.id, user.org_id, user.role, user.email)


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    if settings.auth_mode == "dev":
        org = request.headers.get("x-dev-org", "dev-org")
        role = request.headers.get("x-dev-role", "admin")
        if role not in ROLE_LEVEL:
            raise HTTPException(400, "invalid x-dev-role")
        return _upsert(db, f"dev-{org}-{role}", f"{role}@{org}.local", org, org, role)

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = auth[7:]
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], audience=settings.cognito_client_id, issuer=_issuer()
        )
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}")
    if claims.get("token_use") != "id":
        raise HTTPException(401, "Use the Cognito ID token")
    groups = claims.get("cognito:groups", []) or []
    role = max((g for g in groups if g in ROLE_LEVEL), key=lambda g: ROLE_LEVEL[g], default="viewer")
    sub = claims["sub"]
    org_key = claims.get("custom:org_id") or f"user-{sub}"
    return _upsert(db, sub, claims.get("email", ""), org_key, org_key, role)


def require_role(min_role: str):
    def dep(p: Principal = Depends(get_principal)) -> Principal:
        if ROLE_LEVEL[p.role] < ROLE_LEVEL[min_role]:
            raise HTTPException(403, f"Requires role '{min_role}'")
        return p

    return dep
