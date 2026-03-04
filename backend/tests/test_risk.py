"""Tests for Phase 2: Risk Management."""
import pytest
from decimal import Decimal
from httpx import AsyncClient


# ─── Risk settings endpoints ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_risk_settings_creates_defaults(client: AsyncClient, auth_headers: dict):
    """GET /risk/settings creates and returns default settings for a new user."""
    response = await client.get("/api/v1/risk/settings", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["max_risk_per_trade"] == "500.00"
    assert data["max_risk_daily"] == "1500.00"
    assert data["max_risk_weekly"] == "3000.00"
    assert data["max_risk_monthly"] == "7500.00"
    assert data["use_percentage"] is True
    assert data["circuit_breaker_active"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_get_risk_settings_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/risk/settings")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_risk_settings(client: AsyncClient, auth_headers: dict):
    """PUT /risk/settings updates fields correctly."""
    payload = {
        "max_risk_per_trade": "250.00",
        "max_risk_daily": "750.00",
        "use_percentage": False,
    }
    response = await client.put("/api/v1/risk/settings", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["max_risk_per_trade"] == "250.00"
    assert data["max_risk_daily"] == "750.00"
    assert data["use_percentage"] is False
    assert data["max_risk_weekly"] == "3000.00"  # unchanged


@pytest.mark.asyncio
async def test_update_risk_settings_partial(client: AsyncClient, auth_headers: dict):
    """Only sent fields are updated; others remain at defaults."""
    response = await client.put(
        "/api/v1/risk/settings",
        json={"max_risk_per_trade": "100.00"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["max_risk_per_trade"] == "100.00"
    assert data["max_risk_daily"] == "1500.00"  # unchanged default


@pytest.mark.asyncio
async def test_update_risk_settings_rejects_negative_value(client: AsyncClient, auth_headers: dict):
    """Negative risk limits are rejected with 422."""
    response = await client.put(
        "/api/v1/risk/settings",
        json={"max_risk_per_trade": "-100.00"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "greater than zero" in response.text


@pytest.mark.asyncio
async def test_update_risk_settings_rejects_zero_value(client: AsyncClient, auth_headers: dict):
    """Zero risk limits are rejected with 422."""
    response = await client.put(
        "/api/v1/risk/settings",
        json={"max_risk_daily": "0"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_risk_settings_rejects_invalid_percentage(client: AsyncClient, auth_headers: dict):
    """Percentage > 1 is rejected with 422."""
    response = await client.put(
        "/api/v1/risk/settings",
        json={"max_risk_per_trade_pct": "1.5"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "between 0" in response.text


@pytest.mark.asyncio
async def test_update_risk_settings_rejects_invalid_currency(client: AsyncClient, auth_headers: dict):
    """Non-3-letter currency code is rejected with 422."""
    response = await client.put(
        "/api/v1/risk/settings",
        json={"currency": "NOPE"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_risk_events_empty(client: AsyncClient, auth_headers: dict):
    """GET /risk/events returns empty list initially."""
    response = await client.get("/api/v1/risk/events", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["events"] == []


@pytest.mark.asyncio
async def test_get_risk_events_limit_capped(client: AsyncClient, auth_headers: dict):
    """GET /risk/events rejects limit > 200."""
    response = await client.get("/api/v1/risk/events?limit=9999", headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_risk_events_limit_must_be_positive(client: AsyncClient, auth_headers: dict):
    """GET /risk/events rejects limit < 1."""
    response = await client.get("/api/v1/risk/events?limit=0", headers=auth_headers)
    assert response.status_code == 422


# ─── Circuit breaker ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_activate_circuit_breaker(client: AsyncClient, auth_headers: dict):
    response = await client.post("/api/v1/risk/circuit-breaker/activate", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["circuit_breaker_active"] is True

    settings = await client.get("/api/v1/risk/settings", headers=auth_headers)
    assert settings.json()["circuit_breaker_active"] is True


@pytest.mark.asyncio
async def test_deactivate_circuit_breaker(client: AsyncClient, auth_headers: dict):
    await client.post("/api/v1/risk/circuit-breaker/activate", headers=auth_headers)
    response = await client.post("/api/v1/risk/circuit-breaker/deactivate", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["circuit_breaker_active"] is False


@pytest.mark.asyncio
async def test_circuit_breaker_activate_is_idempotent(client: AsyncClient, auth_headers: dict):
    """Activating twice creates only one circuit_break event."""
    await client.post("/api/v1/risk/circuit-breaker/activate", headers=auth_headers)
    await client.post("/api/v1/risk/circuit-breaker/activate", headers=auth_headers)

    events_resp = await client.get("/api/v1/risk/events", headers=auth_headers)
    events = events_resp.json()["events"]
    circuit_break_events = [e for e in events if e["event_type"] == "circuit_break"]
    assert len(circuit_break_events) == 1


@pytest.mark.asyncio
async def test_circuit_breaker_deactivate_logs_event(client: AsyncClient, auth_headers: dict):
    """Deactivating the circuit breaker creates a deactivation audit event."""
    await client.post("/api/v1/risk/circuit-breaker/activate", headers=auth_headers)
    await client.post("/api/v1/risk/circuit-breaker/deactivate", headers=auth_headers)

    events_resp = await client.get("/api/v1/risk/events", headers=auth_headers)
    events = events_resp.json()["events"]
    circuit_break_events = [e for e in events if e["event_type"] == "circuit_break"]
    assert len(circuit_break_events) == 2  # one activate + one deactivate
    deactivation = next(e for e in circuit_break_events if "deactivated" in (e["message"] or ""))
    assert deactivation is not None


@pytest.mark.asyncio
async def test_deactivate_never_activated_is_idempotent(client: AsyncClient, auth_headers: dict):
    """Deactivating a breaker that was never activated doesn't create an event or error."""
    response = await client.post("/api/v1/risk/circuit-breaker/deactivate", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["circuit_breaker_active"] is False

    events_resp = await client.get("/api/v1/risk/events", headers=auth_headers)
    assert events_resp.json()["events"] == []


@pytest.mark.asyncio
async def test_risk_events_recorded_on_circuit_break(client: AsyncClient, auth_headers: dict):
    """Activating circuit breaker creates a risk event."""
    await client.post("/api/v1/risk/circuit-breaker/activate", headers=auth_headers)
    events_resp = await client.get("/api/v1/risk/events", headers=auth_headers)
    events = events_resp.json()["events"]
    assert len(events) >= 1
    assert events[0]["event_type"] == "circuit_break"
    assert events[0]["limit_type"] == "circuit_breaker"


# ─── Risk service unit tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_pre_trade_passes_under_limit(db_session):
    """validate_pre_trade does not raise when trade_risk is within all limits."""
    from app.risk.service import validate_pre_trade
    import uuid
    user_id = uuid.uuid4()
    await validate_pre_trade(db_session, user_id, Decimal("100.00"), Decimal("50000.00"))


@pytest.mark.asyncio
async def test_validate_pre_trade_fails_per_trade_limit(db_session):
    """validate_pre_trade raises RiskViolation when per-trade limit is exceeded."""
    from app.risk.service import validate_pre_trade, RiskViolation, get_or_create_settings
    import uuid
    user_id = uuid.uuid4()
    settings = await get_or_create_settings(db_session, user_id)
    settings.max_risk_per_trade = Decimal("50.00")
    settings.use_percentage = False
    await db_session.flush()

    with pytest.raises(RiskViolation) as exc_info:
        await validate_pre_trade(db_session, user_id, Decimal("100.00"))
    assert "per-trade limit" in str(exc_info.value)
    assert exc_info.value.limit_type == "per_trade"


@pytest.mark.asyncio
async def test_validate_pre_trade_fails_when_circuit_breaker_active(db_session):
    """validate_pre_trade raises RiskViolation immediately if circuit breaker is on."""
    from app.risk.service import validate_pre_trade, RiskViolation, activate_circuit_breaker
    import uuid
    user_id = uuid.uuid4()
    await activate_circuit_breaker(db_session, user_id)

    with pytest.raises(RiskViolation) as exc_info:
        await validate_pre_trade(db_session, user_id, Decimal("0"), Decimal("50000.00"))
    assert exc_info.value.limit_type == "circuit_breaker"


@pytest.mark.asyncio
async def test_validate_pre_trade_percentage_mode(db_session):
    """Percentage mode limits scale with account equity."""
    from app.risk.service import validate_pre_trade, RiskViolation, get_or_create_settings
    import uuid
    user_id = uuid.uuid4()
    settings = await get_or_create_settings(db_session, user_id)
    settings.use_percentage = True
    # max_risk_per_trade_pct default = 0.01 (1%), equity=$10,000 → limit=$100
    await db_session.flush()

    await validate_pre_trade(db_session, user_id, Decimal("99.00"), Decimal("10000.00"))

    with pytest.raises(RiskViolation) as exc_info:
        await validate_pre_trade(db_session, user_id, Decimal("101.00"), Decimal("10000.00"))
    assert "per-trade limit" in str(exc_info.value)


@pytest.mark.asyncio
async def test_validate_pre_trade_blocks_when_percentage_mode_and_no_equity(db_session):
    """With use_percentage=True, validate_pre_trade blocks if equity is unavailable."""
    from app.risk.service import validate_pre_trade, RiskViolation, get_or_create_settings
    import uuid
    user_id = uuid.uuid4()
    settings = await get_or_create_settings(db_session, user_id)
    settings.use_percentage = True
    await db_session.flush()

    with pytest.raises(RiskViolation) as exc_info:
        # account_equity=None simulates equity fetch failure
        await validate_pre_trade(db_session, user_id, Decimal("100.00"), None)
    assert "equity is unavailable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_validate_pre_trade_zero_risk_logs_warning_event(db_session):
    """When trade_risk=0 (no stop loss), a warning event is recorded but trade is not blocked."""
    from app.risk.service import validate_pre_trade, get_or_create_settings
    from app.models.risk import RiskEvent
    from sqlalchemy import select
    import uuid
    user_id = uuid.uuid4()
    settings = await get_or_create_settings(db_session, user_id)
    settings.use_percentage = False
    await db_session.flush()

    # Should not raise
    await validate_pre_trade(db_session, user_id, Decimal("0"))

    result = await db_session.execute(
        select(RiskEvent).where(RiskEvent.user_id == user_id)
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "warning"
    assert "stop loss" in events[0].message


@pytest.mark.asyncio
async def test_absolute_mode_no_equity_needed(db_session):
    """In absolute mode, validate_pre_trade works fine without account_equity."""
    from app.risk.service import validate_pre_trade, get_or_create_settings
    import uuid
    user_id = uuid.uuid4()
    settings = await get_or_create_settings(db_session, user_id)
    settings.use_percentage = False
    settings.max_risk_per_trade = Decimal("500.00")
    await db_session.flush()

    # Should not raise — no equity needed in absolute mode
    await validate_pre_trade(db_session, user_id, Decimal("100.00"), None)
