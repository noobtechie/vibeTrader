"""Tests for Phase 7: Data Sources & Dashboard."""
import pytest
import uuid
from httpx import AsyncClient


# ─── Data Source Config CRUD ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_data_source_config(client: AsyncClient, auth_headers: dict):
    """Create a questrade data source config."""
    response = await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "questrade", "is_default": True},
        headers=auth_headers,
    )
    assert response.status_code == 201
    cfg = response.json()["config"]
    assert cfg["source_type"] == "questrade"
    assert cfg["is_default"] is True
    assert cfg["is_active"] is True


@pytest.mark.asyncio
async def test_create_data_source_invalid_type(client: AsyncClient, auth_headers: dict):
    """Unknown source_type returns 422."""
    response = await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "nonexistent_broker"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_data_source_configs(client: AsyncClient, auth_headers: dict):
    """List returns all configs for current user."""
    await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "questrade"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "polygon"},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/data-sources/configs", headers=auth_headers)
    assert response.status_code == 200
    configs = response.json()["configs"]
    source_types = {c["source_type"] for c in configs}
    assert "questrade" in source_types
    assert "polygon" in source_types


@pytest.mark.asyncio
async def test_get_data_source_config(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "alpha_vantage"},
        headers=auth_headers,
    )
    config_id = create_resp.json()["config"]["id"]
    response = await client.get(f"/api/v1/data-sources/configs/{config_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["config"]["id"] == config_id


@pytest.mark.asyncio
async def test_get_data_source_config_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        f"/api/v1/data-sources/configs/{uuid.uuid4()}", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_data_source_config(client: AsyncClient, auth_headers: dict):
    """Toggle is_active off."""
    create_resp = await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "polygon"},
        headers=auth_headers,
    )
    config_id = create_resp.json()["config"]["id"]
    response = await client.patch(
        f"/api/v1/data-sources/configs/{config_id}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["config"]["is_active"] is False


@pytest.mark.asyncio
async def test_set_default_clears_previous_default(client: AsyncClient, auth_headers: dict):
    """Setting a new default config clears the previous one."""
    resp1 = await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "questrade", "is_default": True},
        headers=auth_headers,
    )
    cfg1_id = resp1.json()["config"]["id"]

    resp2 = await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "polygon", "is_default": True},
        headers=auth_headers,
    )
    assert resp2.json()["config"]["is_default"] is True

    # First config should no longer be default
    get_resp = await client.get(f"/api/v1/data-sources/configs/{cfg1_id}", headers=auth_headers)
    assert get_resp.json()["config"]["is_default"] is False


@pytest.mark.asyncio
async def test_delete_data_source_config(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "yahoo_finance"},
        headers=auth_headers,
    )
    config_id = create_resp.json()["config"]["id"]

    del_resp = await client.delete(
        f"/api/v1/data-sources/configs/{config_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/data-sources/configs/{config_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_data_source_config_isolation(client: AsyncClient, auth_headers: dict):
    """User B cannot see or modify User A's configs."""
    create_resp = await client.post(
        "/api/v1/data-sources/configs",
        json={"source_type": "questrade"},
        headers=auth_headers,
    )
    config_id = create_resp.json()["config"]["id"]

    # Register user B
    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb_datasource@example.com", "password": "Password123!"},
    )
    login_b = await client.post(
        "/api/v1/auth/login",
        json={"email": "userb_datasource@example.com", "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    response = await client.get(
        f"/api/v1/data-sources/configs/{config_id}", headers=headers_b
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_data_source_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/data-sources/configs")
    assert response.status_code == 403


# ─── Comprehensive Dashboard ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_structure(client: AsyncClient, auth_headers: dict):
    """Dashboard returns all expected top-level sections."""
    response = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    for section in ("portfolio", "trades_summary", "signals_24h", "strategies",
                    "risk", "journal", "backtests", "recent_signals", "recent_trades"):
        assert section in data, f"Missing section: {section}"


@pytest.mark.asyncio
async def test_dashboard_portfolio_section(client: AsyncClient, auth_headers: dict):
    """Portfolio section has required fields."""
    response = await client.get("/api/v1/dashboard", headers=auth_headers)
    portfolio = response.json()["portfolio"]
    assert "open_positions" in portfolio
    assert "total_realized_pnl" in portfolio
    assert "unrealized_pnl" in portfolio
    assert "unrealized_pnl_available" in portfolio
    assert portfolio["open_positions"] >= 0
    assert portfolio["unrealized_pnl_available"] is False


@pytest.mark.asyncio
async def test_dashboard_signals_24h_section(client: AsyncClient, auth_headers: dict):
    """signals_24h section has all status keys."""
    response = await client.get("/api/v1/dashboard", headers=auth_headers)
    counts = response.json()["signals_24h"]
    for key in ("pending", "executed", "rejected", "expired"):
        assert key in counts


@pytest.mark.asyncio
async def test_dashboard_risk_section(client: AsyncClient, auth_headers: dict):
    """Risk section reflects circuit_breaker status."""
    response = await client.get("/api/v1/dashboard", headers=auth_headers)
    risk = response.json()["risk"]
    assert "circuit_breaker_active" in risk
    assert "risk_events_24h" in risk
    assert risk["circuit_breaker_active"] is False  # No circuit break triggered


@pytest.mark.asyncio
async def test_dashboard_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_recent_signals_populated(client: AsyncClient, auth_headers: dict):
    """recent_signals list updates after a scan."""

    def _breakout_candles():
        candles = [{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 500}
                   for _ in range(25)]
        candles.append({"open": 101.0, "high": 110.0, "low": 100.0, "close": 108.0, "volume": 3000})
        return candles

    await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(), "pattern_name": "breakout"},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert response.status_code == 200
    recent = response.json()["recent_signals"]
    assert len(recent) >= 1
    assert recent[0]["symbol"] == "SPY"
