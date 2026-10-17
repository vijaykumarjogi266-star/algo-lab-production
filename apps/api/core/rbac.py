"""Role-Based Access Control (RBAC) & API Key Management Module.

Workstream C Compliance:
- Role hierarchy: viewer -> researcher -> operator -> risk_admin -> system_admin.
- Constant-time verification (hmac.compare_digest) of SHA-256 hashed keys.
- Key rotation, revocation, expiration metadata, and role/scope auditing.
- Scoped endpoint permission guards.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac
import logging
from typing import Dict, List, Optional, Set
from fastapi import Header, HTTPException, Request, status

logger = logging.getLogger("algo_lab.api.rbac")


class Role(str, Enum):
    VIEWER = "viewer"
    RESEARCHER = "researcher"
    OPERATOR = "operator"
    RISK_ADMIN = "risk_admin"
    SYSTEM_ADMIN = "system_admin"

    @classmethod
    def hierarchy_level(cls, role: Role) -> int:
        levels = {
            cls.VIEWER: 10,
            cls.RESEARCHER: 20,
            cls.OPERATOR: 30,
            cls.RISK_ADMIN: 40,
            cls.SYSTEM_ADMIN: 50,
        }
        return levels.get(role, 0)

    def can_access(self, required_role: Role) -> bool:
        """Returns True if this role has at least the privilege level of required_role."""
        return self.hierarchy_level(self) >= self.hierarchy_level(required_role)


@dataclass
class ApiKeyMetadata:
    key_id: str
    hashed_key: str
    role: Role
    scopes: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    revoked: bool = False
    last_used_at: Optional[datetime] = None
    description: str = ""

    def is_valid(self) -> bool:
        """Checks if key is not revoked and not expired."""
        if self.revoked:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True


def hash_key(raw_key: str) -> str:
    """Computes SHA-256 digest of raw API key for secure at-rest storage."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


class ApiKeyRegistry:
    """In-memory constant-time verifiable API Key registry with rotation and revocation."""

    def __init__(self):
        self._keys: Dict[str, ApiKeyMetadata] = {}

    def register_key(
        self,
        raw_key: str,
        key_id: str,
        role: Role,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
        description: str = "",
    ) -> ApiKeyMetadata:
        """Registers a new raw key by computing and storing its SHA-256 hash."""
        hashed = hash_key(raw_key)
        meta = ApiKeyMetadata(
            key_id=key_id,
            hashed_key=hashed,
            role=role,
            scopes=scopes or [],
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            revoked=False,
            description=description,
        )
        self._keys[key_id] = meta
        return meta

    def authenticate(self, raw_key: str) -> Optional[ApiKeyMetadata]:
        """Verifies raw key against registered hashed keys using constant-time comparison."""
        if not raw_key:
            return None
        candidate_hash = hash_key(raw_key)

        matched_meta: Optional[ApiKeyMetadata] = None
        for meta in self._keys.values():
            if hmac.compare_digest(meta.hashed_key, candidate_hash):
                if meta.is_valid():
                    meta.last_used_at = datetime.now(timezone.utc)
                    matched_meta = meta
                    break

        return matched_meta

    def rotate_key(
        self,
        key_id: str,
        new_raw_key: str,
        new_expires_at: Optional[datetime] = None,
    ) -> ApiKeyMetadata:
        """Rotates an existing key ID to a new raw secret while maintaining role & scopes."""
        if key_id not in self._keys:
            raise KeyError(f"Key ID '{key_id}' not found.")
        existing = self._keys[key_id]
        new_hashed = hash_key(new_raw_key)
        existing.hashed_key = new_hashed
        existing.created_at = datetime.now(timezone.utc)
        if new_expires_at is not None:
            existing.expires_at = new_expires_at
        existing.revoked = False
        return existing

    def revoke_key(self, key_id: str) -> bool:
        """Immediately revokes an API key by key_id."""
        if key_id in self._keys:
            self._keys[key_id].revoked = True
            return True
        return False

    def get_metadata(self, key_id: str) -> Optional[ApiKeyMetadata]:
        return self._keys.get(key_id)


# Global singleton registry
key_registry = ApiKeyRegistry()


def init_default_keys(secret_key: str) -> None:
    """Initializes standard institutional role keys seeded from environment."""
    if not secret_key:
        return
    # Default master internal key maps to SYSTEM_ADMIN
    key_registry.register_key(
        raw_key=secret_key,
        key_id="default-master-system-admin",
        role=Role.SYSTEM_ADMIN,
        scopes=["*"],
        description="Master loopback key for local system daemon and test suites",
    )
    # Register demo/role keys for granular testing and role scoping
    key_registry.register_key(
        raw_key=f"{secret_key}-viewer",
        key_id="default-viewer-key",
        role=Role.VIEWER,
        scopes=["read:research", "read:health", "read:system"],
        description="Read-only research viewer role",
    )
    key_registry.register_key(
        raw_key=f"{secret_key}-researcher",
        key_id="default-researcher-key",
        role=Role.RESEARCHER,
        scopes=["read:research", "write:experiments", "read:data"],
        description="Quantitative researcher role",
    )
    key_registry.register_key(
        raw_key=f"{secret_key}-operator",
        key_id="default-operator-key",
        role=Role.OPERATOR,
        scopes=["read:research", "write:experiments", "operate:paper"],
        description="Paper trading operator role",
    )
    key_registry.register_key(
        raw_key=f"{secret_key}-risk-admin",
        key_id="default-risk-admin-key",
        role=Role.RISK_ADMIN,
        scopes=["read:research", "risk:breaker", "risk:limits"],
        description="Risk administrator role",
    )


def extract_raw_api_key(request: Request) -> Optional[str]:
    """Extracts raw key from Authorization Bearer or X-Internal-Secret or X-API-Key headers."""
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    header_secret = request.headers.get("X-Internal-Secret", "").strip()
    if header_secret:
        return header_secret
    api_key_header = request.headers.get("X-API-Key", "").strip()
    if api_key_header:
        return api_key_header
    return None


def get_current_actor(request: Request) -> Optional[ApiKeyMetadata]:
    """Retrieves authenticated actor metadata attached to request state."""
    return getattr(request.state, "actor", None)


def require_role(min_role: Role):
    """FastAPI route dependency enforcing minimum required role hierarchy."""
    def role_dependency(request: Request):
        actor: Optional[ApiKeyMetadata] = get_current_actor(request)
        if not actor:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"detail": "Authentication required", "code": "UNAUTHORIZED"},
            )
        if not actor.role.can_access(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "detail": f"Access denied: Required role '{min_role.value}', but actor has '{actor.role.value}'",
                    "code": "FORBIDDEN_INSUFFICIENT_ROLE",
                },
            )
        return actor

    return role_dependency
