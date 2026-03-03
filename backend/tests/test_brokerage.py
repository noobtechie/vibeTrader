"""Tests for brokerage connection endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_connection_status_not_connected(client: AsyncClient, auth_headers: dict):
    """User has no brokerage connection by default."""
    response = await client.get("/api/v1/brokerage/status", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["is_connected"] is False


@pytest.mark.asyncio
async def test_connect_questrade_invalid_token(client: AsyncClient, auth_headers: dict):
    """Using a bad refresh token should fail."""
    response = await client.post(
        "/api/v1/brokerage/connect/questrade",
        headers=auth_headers,
        json={"refresh_token": "invalid-token"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_disconnect_no_connection(client: AsyncClient, auth_headers: dict):
    """Disconnecting when not connected should succeed gracefully."""
    response = await client.delete("/api/v1/brokerage/disconnect", headers=auth_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_accounts_no_connection(client: AsyncClient, auth_headers: dict):
    """Getting accounts without connection returns 404."""
    response = await client.get("/api/v1/brokerage/accounts", headers=auth_headers)
    assert response.status_code == 404
