"""Data Source Configuration API."""
import uuid
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import CurrentUser
from app.enums import DataSourceType
from app.models.market_data import DataSourceConfig

router = APIRouter(prefix="/data-sources", tags=["data_sources"])

_VALID_SOURCE_TYPES = frozenset(t.value for t in DataSourceType)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class DataSourceConfigCreate(BaseModel):
    source_type: str
    config: Optional[dict] = None
    is_default: bool = False

    model_config = {"extra": "forbid"}

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        if v not in _VALID_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(_VALID_SOURCE_TYPES)}")
        return v


class DataSourceConfigUpdate(BaseModel):
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    config: Optional[dict] = None

    model_config = {"extra": "forbid"}


def _config_dict(c: DataSourceConfig) -> dict:
    return {
        "id": str(c.id),
        "user_id": str(c.user_id),
        "source_type": c.source_type,
        "is_default": c.is_default,
        "is_active": c.is_active,
        "config": c.config,
        "created_at": c.created_at.isoformat(),
    }


async def _get_config_or_404(
    db: AsyncSession, config_id: uuid.UUID, user_id: uuid.UUID
) -> DataSourceConfig:
    result = await db.execute(
        select(DataSourceConfig).where(
            DataSourceConfig.id == config_id,
            DataSourceConfig.user_id == user_id,
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Data source config not found")
    return cfg


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/configs", status_code=status.HTTP_201_CREATED)
async def create_config(
    body: DataSourceConfigCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Register a new data source configuration for the current user.

    If `is_default=True`, any existing default is cleared first.
    Credentials are not accepted via this endpoint (use secure credential storage).
    """
    if body.is_default:
        # Clear existing default for this user
        existing_defaults = await db.execute(
            select(DataSourceConfig).where(
                DataSourceConfig.user_id == current_user.id,
                DataSourceConfig.is_default.is_(True),
            )
        )
        for existing in existing_defaults.scalars().all():
            existing.is_default = False

    cfg = DataSourceConfig(
        user_id=current_user.id,
        source_type=body.source_type,
        config=body.config,
        is_default=body.is_default,
    )
    db.add(cfg)
    await db.flush()
    return {"config": _config_dict(cfg)}


@router.get("/configs")
async def list_configs(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all data source configurations for the current user."""
    result = await db.execute(
        select(DataSourceConfig)
        .where(DataSourceConfig.user_id == current_user.id)
        .order_by(DataSourceConfig.is_default.desc(), DataSourceConfig.created_at.asc())
    )
    configs = result.scalars().all()
    return {"configs": [_config_dict(c) for c in configs]}


@router.get("/configs/{config_id}")
async def get_config(
    config_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    cfg = await _get_config_or_404(db, config_id, current_user.id)
    return {"config": _config_dict(cfg)}


@router.patch("/configs/{config_id}")
async def update_config(
    config_id: uuid.UUID,
    body: DataSourceConfigUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update is_default, is_active, or config dict. Setting is_default=True clears existing default."""
    cfg = await _get_config_or_404(db, config_id, current_user.id)

    data = body.model_dump(exclude_unset=True)

    if data.get("is_default") is True:
        existing_defaults = await db.execute(
            select(DataSourceConfig).where(
                DataSourceConfig.user_id == current_user.id,
                DataSourceConfig.is_default.is_(True),
                DataSourceConfig.id != config_id,
            )
        )
        for existing in existing_defaults.scalars().all():
            existing.is_default = False

    for key, val in data.items():
        setattr(cfg, key, val)

    await db.flush()
    return {"config": _config_dict(cfg)}


@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    config_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a data source configuration."""
    cfg = await _get_config_or_404(db, config_id, current_user.id)
    await db.delete(cfg)
