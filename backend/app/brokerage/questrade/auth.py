"""Questrade OAuth2 token management with encrypted storage."""
from datetime import datetime, timedelta
from typing import Optional
import uuid
import httpx
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.models.user import BrokerageConnection, BrokerType


def _get_fernet() -> Fernet:
    """
    Get Fernet instance. Fernet requires a URL-safe base64-encoded 32-byte key.
    The encryption_key setting must be exactly 32 ASCII characters; it is used
    directly as the 32-byte secret, then base64-encoded to produce a valid key.
    """
    raw = settings.encryption_key.encode("ascii")
    if len(raw) != 32:
        raise ValueError(
            f"ENCRYPTION_KEY must be exactly 32 ASCII characters, got {len(raw)}. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(24)[:32])\""
        )
    import base64
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_token(token: str) -> str:
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


async def get_active_connection(
    db: AsyncSession, user_id: uuid.UUID
) -> Optional[BrokerageConnection]:
    result = await db.execute(
        select(BrokerageConnection).where(
            BrokerageConnection.user_id == user_id,
            BrokerageConnection.broker_type == BrokerType.questrade.value,
            BrokerageConnection.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def store_tokens(
    db: AsyncSession,
    user_id: uuid.UUID,
    access_token: str,
    refresh_token: str,
    api_server: str,
    expires_in: int,
) -> BrokerageConnection:
    """Store encrypted tokens in the database."""
    existing = await get_active_connection(db, user_id)
    if existing:
        existing.is_active = False
        await db.flush()

    connection = BrokerageConnection(
        user_id=user_id,
        broker_type=BrokerType.questrade.value,
        access_token_encrypted=encrypt_token(access_token),
        refresh_token_encrypted=encrypt_token(refresh_token),
        api_server=api_server.rstrip("/"),
        expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
        is_active=True,
    )
    db.add(connection)
    await db.flush()
    await db.refresh(connection)
    return connection


async def refresh_questrade_token(
    db: AsyncSession,
    connection: BrokerageConnection,
) -> Optional[BrokerageConnection]:
    """Use the refresh token to get a new access token."""
    if not connection.refresh_token_encrypted:
        return None

    refresh_token = decrypt_token(connection.refresh_token_encrypted)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                settings.questrade_auth_url,
                params={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, KeyError):
            return None

    connection.access_token_encrypted = encrypt_token(data["access_token"])
    connection.refresh_token_encrypted = encrypt_token(data["refresh_token"])
    connection.api_server = data["api_server"].rstrip("/")
    connection.expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"])
    await db.flush()
    return connection


async def exchange_code_for_tokens(
    db: AsyncSession,
    user_id: uuid.UUID,
    refresh_token: str,
) -> BrokerageConnection:
    """
    Questrade uses refresh tokens directly (not auth codes).
    The user copies their refresh token from the Questrade API hub.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.questrade_auth_url,
            params={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

    return await store_tokens(
        db=db,
        user_id=user_id,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        api_server=data["api_server"],
        expires_in=data["expires_in"],
    )
