import ipaddress
import socket
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.config import settings
from app.models import AuditLog, Dataset


def audit(db: Session, p: Principal, action: str, detail: dict | None = None) -> None:
    db.add(AuditLog(org_id=p.org_id, user_id=p.user_id, action=action, detail=detail or {}))
    db.commit()


def assert_public_host(host: str | None) -> None:
    """SSRF guard for user-supplied DB/API endpoints."""
    if settings.allow_private_hosts:
        return
    if not host:
        raise HTTPException(400, "Missing host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(400, f"Cannot resolve host {host}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(400, "Private or internal network addresses are not allowed")


def new_table_name(db: Session, org_id: str, base: str) -> str:
    import re

    s = re.sub(r"[^0-9a-z]+", "_", base.lower()).strip("_") or "dataset"
    if s[0].isdigit():
        s = "t_" + s
    s = s[:60]
    existing = set(db.scalars(select(Dataset.table_name).where(Dataset.org_id == org_id)))
    name, i = s, 2
    while name in existing:
        name, i = f"{s}_{i}", i + 1
    return name


def new_dataset_id() -> str:
    return uuid.uuid4().hex
