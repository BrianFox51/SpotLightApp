"""Encrypted, versioned storage for Spotlight's server-owned provider credentials."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Account, AuditLog, ProviderSecretVersion

SUPPORTED_PROVIDERS = {
    "ticketmaster": "Ticketmaster Discovery API key",
    "tmdb": "TMDB API key or read access token",
    "watchmode": "Watchmode API key",
    "igdb_client_id": "Twitch/IGDB client ID",
    "igdb_client_secret": "Twitch/IGDB client secret",
    "youtube": "YouTube Data API key (optional; not currently used)",
    "spotify_client_id": "Spotify client ID (planned)",
    "spotify_client_secret": "Spotify client secret (planned)",
}


class ProviderSecretError(ValueError):
    pass


def _cipher() -> Fernet:
    key = settings.provider_secrets_encryption_key.strip()
    if not key:
        raise ProviderSecretError(
            "Provider secret storage is not initialized. Set PROVIDER_SECRETS_ENCRYPTION_KEY on the server."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ProviderSecretError("PROVIDER_SECRETS_ENCRYPTION_KEY is invalid.") from exc


def normalize_provider(provider: str) -> str:
    value = str(provider or "").strip().lower()
    if value not in SUPPORTED_PROVIDERS:
        choices = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise ProviderSecretError(f"Unknown provider key '{value}'. Supported names: {choices}")
    return value


def _next_version(db: Session, provider: str) -> int:
    current = db.scalar(
        select(func.max(ProviderSecretVersion.version)).where(ProviderSecretVersion.provider == provider)
    )
    return int(current or 0) + 1


def _record(db: Session, provider: str, value: str | None, actor: Account, note: str) -> ProviderSecretVersion:
    provider = normalize_provider(provider)
    if value is None:
        ciphertext = fingerprint = None
    else:
        value = value.strip()
        if not value:
            raise ProviderSecretError("A provider secret cannot be blank; use clear to record a removal.")
        ciphertext = _cipher().encrypt(value.encode("utf-8")).decode("ascii")
        fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    row = ProviderSecretVersion(
        provider=provider,
        version=_next_version(db, provider),
        ciphertext=ciphertext,
        fingerprint=fingerprint,
        change_note=str(note or "")[:500],
        actor_id=actor.id,
    )
    db.add(row)
    db.flush()
    db.add(AuditLog(
        actor_id=actor.id,
        action="provider_secret.cleared" if value is None else "provider_secret.changed",
        entity_type="provider_secret_version",
        entity_id=row.id,
        details=f"{provider} version {row.version}" + (f"; fingerprint {fingerprint}" if fingerprint else ""),
    ))
    db.commit()
    db.refresh(row)
    return row


def set_provider_secret(db: Session, provider: str, value: str, actor: Account, note: str = "") -> ProviderSecretVersion:
    return _record(db, provider, value, actor, note)


def clear_provider_secret(db: Session, provider: str, actor: Account, note: str = "") -> ProviderSecretVersion:
    return _record(db, provider, None, actor, note)


def restore_provider_secret(db: Session, provider: str, version: int, actor: Account, note: str = "") -> ProviderSecretVersion:
    provider = normalize_provider(provider)
    old = db.scalar(select(ProviderSecretVersion).where(
        ProviderSecretVersion.provider == provider,
        ProviderSecretVersion.version == version,
    ))
    if old is None:
        raise ProviderSecretError("That secret version does not exist.")
    if old.ciphertext is None:
        raise ProviderSecretError("That version records a cleared key and cannot be restored as a secret.")
    try:
        value = _cipher().decrypt(old.ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ProviderSecretError("Could not decrypt that version; check the server encryption key.") from exc
    return _record(db, provider, value, actor, note or f"Restored previous version {version}")


def current_provider_secret(db: Session, provider: str) -> str | None:
    """Internal server use only. Never include this value in API responses or logs."""
    provider = normalize_provider(provider)
    row = db.scalar(select(ProviderSecretVersion).where(
        ProviderSecretVersion.provider == provider,
    ).order_by(ProviderSecretVersion.version.desc()).limit(1))
    if row is None or row.ciphertext is None:
        return None
    try:
        return _cipher().decrypt(row.ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ProviderSecretError("Could not decrypt the current key; check the server encryption key.") from exc


def provider_secret_history(db: Session, provider: str) -> list[dict[str, object]]:
    provider = normalize_provider(provider)
    rows = db.scalars(select(ProviderSecretVersion).where(
        ProviderSecretVersion.provider == provider,
    ).order_by(ProviderSecretVersion.version.desc())).all()
    return [{
        "provider": row.provider,
        "version": row.version,
        "configured": row.ciphertext is not None,
        "fingerprint": row.fingerprint,
        "change_note": row.change_note,
        "created_at": row.created_at.astimezone(timezone.utc).isoformat(),
        "actor_id": row.actor_id,
    } for row in rows]


def provider_secret_status(db: Session) -> list[dict[str, object]]:
    return [{
        "provider": provider,
        "label": label,
        "configured": (history[0]["configured"] if history else False),
        "current_version": (history[0]["version"] if history else None),
        "versions": len(history),
    } for provider, label in SUPPORTED_PROVIDERS.items()
      for history in [provider_secret_history(db, provider)]]
