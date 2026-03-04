"""Tests for Phase 6: Automation & Scanning."""
import pytest
import uuid
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.automation.scanner import scan


# ─── Synthetic data helpers ───────────────────────────────────────────────────

def _flat_candles(n: int, price: float = 100.0) -> list[dict]:
    return [{"open": price, "high": price + 0.5, "low": price - 0.5, "close": price, "volume": 1000}
            for _ in range(n)]


def _breakout_candles(consolidation: int = 25, price: float = 100.0) -> list[dict]:
    candles = [{"open": price, "high": price + 1, "low": price - 1, "close": price, "volume": 500}
               for _ in range(consolidation)]
    candles.append({"open": price + 1, "high": 110.0, "low": price, "close": 108.0, "volume": 3000})
    return candles


def _volume_spike_candles(n: int = 25, base_volume: int = 1000, spike_volume: int = 5000) -> list[dict]:
    candles = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": base_volume}
               for _ in range(n)]
    candles.append({"open": 100, "high": 102, "low": 99, "close": 101, "volume": spike_volume})
    return candles


# ─── Scanner unit tests ───────────────────────────────────────────────────────

def test_scan_no_signal_flat():
    result = scan("pin_bar", _flat_candles(30))
    assert result.detected is False
    assert result.confidence == 0.0


def test_scan_breakout_detected():
    candles = _breakout_candles(25)
    result = scan("breakout", candles)
    assert result.detected is True
    assert result.direction == "bullish"
    assert 0.0 < result.confidence <= 100.0
    assert "breakout_price" in result.meta


def test_scan_volume_spike_detected():
    candles = _volume_spike_candles(25, base_volume=1000, spike_volume=5000)
    result = scan("volume_spike", candles)
    assert result.detected is True
    assert result.direction == "bullish"
    assert result.confidence > 0


def test_scan_empty_candles():
    result = scan("breakout", [])
    assert result.detected is False


def test_scan_unknown_pattern_raises():
    with pytest.raises(ValueError, match="Unknown pattern"):
        scan("magic_wand", _flat_candles(10))


def test_scan_all_valid_patterns_run():
    candles = _flat_candles(60)
    for pattern in ("pin_bar", "breakout", "flag", "vwap_bounce", "volume_spike"):
        result = scan(pattern, candles)
        assert hasattr(result, "detected")
        assert 0.0 <= result.confidence <= 100.0


# ─── API endpoint tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_no_detection(client: AsyncClient, auth_headers: dict):
    """Flat candles produce no signal; endpoint returns detected=False."""
    payload = {
        "symbol": "AAPL",
        "candles": _flat_candles(50),
        "pattern_name": "pin_bar",
    }
    response = await client.post("/api/v1/automation/scan", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["detected"] is False
    assert data["signal"] is None


@pytest.mark.asyncio
async def test_scan_creates_pending_signal(client: AsyncClient, auth_headers: dict):
    """Detected pattern with semi_auto mode creates a pending signal."""
    payload = {
        "symbol": "SPY",
        "candles": _breakout_candles(25),
        "pattern_name": "breakout",
        "automation_mode": "semi_auto",
    }
    response = await client.post("/api/v1/automation/scan", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["detected"] is True
    sig = data["signal"]
    assert sig["symbol"] == "SPY"
    assert sig["pattern_name"] == "breakout"
    assert sig["status"] == "pending"
    assert sig["direction"] == "bullish"
    assert sig["confidence_score"] > 0


@pytest.mark.asyncio
async def test_scan_full_auto_creates_executed_signal(client: AsyncClient, auth_headers: dict):
    """full_auto mode creates a signal with status='executed'."""
    payload = {
        "symbol": "QQQ",
        "candles": _breakout_candles(25),
        "pattern_name": "breakout",
        "automation_mode": "full_auto",
    }
    response = await client.post("/api/v1/automation/scan", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    sig = data["signal"]
    assert sig["status"] == "executed"
    assert sig["execution_note"] is not None


@pytest.mark.asyncio
async def test_scan_unknown_pattern_returns_422(client: AsyncClient, auth_headers: dict):
    payload = {
        "symbol": "AAPL",
        "candles": _flat_candles(10),
        "pattern_name": "nonexistent",
    }
    response = await client.post("/api/v1/automation/scan", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_scan_requires_auth(client: AsyncClient):
    payload = {"symbol": "AAPL", "candles": _flat_candles(5), "pattern_name": "breakout"}
    response = await client.post("/api/v1/automation/scan", json=payload)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_scan_invalid_symbol(client: AsyncClient, auth_headers: dict):
    payload = {
        "symbol": "=EVIL()",
        "candles": _flat_candles(10),
        "pattern_name": "breakout",
    }
    response = await client.post("/api/v1/automation/scan", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_signals_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/automation/signals", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["signals"] == []


@pytest.mark.asyncio
async def test_list_signals_filter_by_status(client: AsyncClient, auth_headers: dict):
    """Create one pending signal, then filter by status."""
    await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25),
              "pattern_name": "breakout", "automation_mode": "semi_auto"},
        headers=auth_headers,
    )
    response = await client.get(
        "/api/v1/automation/signals?status=pending", headers=auth_headers
    )
    assert response.status_code == 200
    signals = response.json()["signals"]
    assert all(s["status"] == "pending" for s in signals)
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_get_signal(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25), "pattern_name": "breakout"},
        headers=auth_headers,
    )
    signal_id = resp.json()["signal"]["id"]
    response = await client.get(f"/api/v1/automation/signals/{signal_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["signal"]["id"] == signal_id


@pytest.mark.asyncio
async def test_get_signal_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        f"/api/v1/automation/signals/{uuid.uuid4()}", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_confirm_signal(client: AsyncClient, auth_headers: dict):
    """Confirm a pending signal → status becomes 'executed'."""
    scan_resp = await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25),
              "pattern_name": "breakout", "automation_mode": "semi_auto"},
        headers=auth_headers,
    )
    signal_id = scan_resp.json()["signal"]["id"]

    confirm_resp = await client.post(
        f"/api/v1/automation/signals/{signal_id}/confirm", headers=auth_headers
    )
    assert confirm_resp.status_code == 200
    sig = confirm_resp.json()["signal"]
    assert sig["status"] == "executed"
    assert sig["resolved_at"] is not None


@pytest.mark.asyncio
async def test_confirm_already_executed_signal(client: AsyncClient, auth_headers: dict):
    """Confirming an already-executed signal returns 409."""
    scan_resp = await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25),
              "pattern_name": "breakout", "automation_mode": "full_auto"},
        headers=auth_headers,
    )
    signal_id = scan_resp.json()["signal"]["id"]

    response = await client.post(
        f"/api/v1/automation/signals/{signal_id}/confirm", headers=auth_headers
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_reject_signal(client: AsyncClient, auth_headers: dict):
    """Reject a pending signal → status becomes 'rejected'."""
    scan_resp = await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25),
              "pattern_name": "breakout", "automation_mode": "semi_auto"},
        headers=auth_headers,
    )
    signal_id = scan_resp.json()["signal"]["id"]

    reject_resp = await client.post(
        f"/api/v1/automation/signals/{signal_id}/reject", headers=auth_headers
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["signal"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_reject_already_rejected_signal(client: AsyncClient, auth_headers: dict):
    """Rejecting an already-rejected signal returns 409."""
    scan_resp = await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25),
              "pattern_name": "breakout", "automation_mode": "semi_auto"},
        headers=auth_headers,
    )
    signal_id = scan_resp.json()["signal"]["id"]

    await client.post(
        f"/api/v1/automation/signals/{signal_id}/reject", headers=auth_headers
    )
    response = await client.post(
        f"/api/v1/automation/signals/{signal_id}/reject", headers=auth_headers
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_signal(client: AsyncClient, auth_headers: dict):
    scan_resp = await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25), "pattern_name": "breakout"},
        headers=auth_headers,
    )
    signal_id = scan_resp.json()["signal"]["id"]

    del_resp = await client.delete(
        f"/api/v1/automation/signals/{signal_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/automation/signals/{signal_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_signal_isolation_between_users(client: AsyncClient, auth_headers: dict):
    """User B cannot access User A's signal."""
    scan_resp = await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25), "pattern_name": "breakout"},
        headers=auth_headers,
    )
    signal_id = scan_resp.json()["signal"]["id"]

    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb_automation@example.com", "password": "Password123!"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "userb_automation@example.com", "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    response = await client.get(
        f"/api/v1/automation/signals/{signal_id}", headers=headers_b
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dashboard(client: AsyncClient, auth_headers: dict):
    """Dashboard endpoint returns expected structure."""
    response = await client.get("/api/v1/automation/dashboard", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "active_strategies" in data
    assert "signal_counts_24h" in data
    assert "recent_signals" in data
    counts = data["signal_counts_24h"]
    for key in ("pending", "executed", "rejected", "expired"):
        assert key in counts


@pytest.mark.asyncio
async def test_dashboard_reflects_signal_creation(client: AsyncClient, auth_headers: dict):
    """After creating a signal, dashboard signal counts update."""
    before = await client.get("/api/v1/automation/dashboard", headers=auth_headers)
    pending_before = before.json()["signal_counts_24h"]["pending"]

    await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25),
              "pattern_name": "breakout", "automation_mode": "semi_auto"},
        headers=auth_headers,
    )

    after = await client.get("/api/v1/automation/dashboard", headers=auth_headers)
    pending_after = after.json()["signal_counts_24h"]["pending"]
    assert pending_after >= pending_before + 1


@pytest.mark.asyncio
async def test_invalid_status_filter_returns_422(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/automation/signals?status=magic", headers=auth_headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_scan_non_numeric_pattern_params_returns_422(client: AsyncClient, auth_headers: dict):
    """Non-numeric pattern_params values are rejected at schema level."""
    payload = {
        "symbol": "SPY",
        "candles": _breakout_candles(25),
        "pattern_name": "breakout",
        "pattern_params": {"lookback": "notanumber"},
    }
    response = await client.post("/api/v1/automation/scan", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_scan_unknown_pattern_params_key_returns_422(client: AsyncClient, auth_headers: dict):
    """Unknown pattern_params keys are rejected by the scanner's allowlist."""
    payload = {
        "symbol": "SPY",
        "candles": _breakout_candles(25),
        "pattern_name": "breakout",
        "pattern_params": {"invalid_key": 5},
    }
    response = await client.post("/api/v1/automation/scan", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_signals_filter_by_symbol(client: AsyncClient, auth_headers: dict):
    """list_signals symbol filter returns only matching symbols."""
    await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "AAPL", "candles": _breakout_candles(25), "pattern_name": "breakout"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25), "pattern_name": "breakout"},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/automation/signals?symbol=AAPL", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert all(s["symbol"] == "AAPL" for s in data["signals"])


@pytest.mark.asyncio
async def test_list_signals_returns_total(client: AsyncClient, auth_headers: dict):
    """list_signals response includes a total count for pagination."""
    await client.post(
        "/api/v1/automation/scan",
        json={"symbol": "SPY", "candles": _breakout_candles(25), "pattern_name": "breakout",
              "automation_mode": "semi_auto"},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/automation/signals?limit=1&offset=0", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert data["total"] >= 1
    assert data["count"] == len(data["signals"])


@pytest.mark.asyncio
async def test_scan_strategy_id_cross_user_returns_404(client: AsyncClient, auth_headers: dict):
    """Providing a strategy_id owned by a different user returns 404."""
    # Register user B and create a playbook + strategy as user B
    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb_strat@example.com", "password": "Password123!"},
    )
    login_b = await client.post(
        "/api/v1/auth/login",
        json={"email": "userb_strat@example.com", "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    pb_resp = await client.post(
        "/api/v1/strategies/playbooks",
        json={"name": "B Playbook"},
        headers=headers_b,
    )
    playbook_id = pb_resp.json()["playbook"]["id"]
    strat_resp = await client.post(
        f"/api/v1/strategies/playbooks/{playbook_id}/strategies",
        json={"name": "B Strategy"},
        headers=headers_b,
    )
    strategy_id = strat_resp.json()["strategy"]["id"]

    # User A tries to scan with user B's strategy_id
    response = await client.post(
        "/api/v1/automation/scan",
        json={
            "symbol": "SPY",
            "candles": _breakout_candles(25),
            "pattern_name": "breakout",
            "strategy_id": strategy_id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 404
