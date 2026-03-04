"""Tests for Phase 3: Strategy Playbook."""
import pytest
from decimal import Decimal
from httpx import AsyncClient


# ─── Playbook CRUD ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_playbooks_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/strategies/playbooks", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["playbooks"] == []


@pytest.mark.asyncio
async def test_create_playbook(client: AsyncClient, auth_headers: dict):
    payload = {
        "name": "Momentum Breakout",
        "description": "Trade breakouts with volume confirmation",
        "goals": {"target_r": 3, "win_rate": 0.45},
        "context_rules": [{"type": "trend", "condition": "uptrend"}],
        "trigger_rules": [{"pattern": "breakout", "volume_confirm": True}],
    }
    response = await client.post("/api/v1/strategies/playbooks", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()["playbook"]
    assert data["name"] == "Momentum Breakout"
    assert data["goals"]["target_r"] == 3
    assert "id" in data


@pytest.mark.asyncio
async def test_get_playbook(client: AsyncClient, auth_headers: dict):
    # Create first
    resp = await client.post(
        "/api/v1/strategies/playbooks",
        json={"name": "Test Playbook"},
        headers=auth_headers,
    )
    pb_id = resp.json()["playbook"]["id"]

    response = await client.get(f"/api/v1/strategies/playbooks/{pb_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["playbook"]["id"] == pb_id


@pytest.mark.asyncio
async def test_get_playbook_not_found(client: AsyncClient, auth_headers: dict):
    import uuid
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/strategies/playbooks/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_playbook(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/strategies/playbooks",
        json={"name": "Original Name"},
        headers=auth_headers,
    )
    pb_id = resp.json()["playbook"]["id"]

    response = await client.put(
        f"/api/v1/strategies/playbooks/{pb_id}",
        json={"name": "Updated Name", "theory": "Price action first"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["playbook"]
    assert data["name"] == "Updated Name"
    assert data["theory"] == "Price action first"


@pytest.mark.asyncio
async def test_delete_playbook(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/strategies/playbooks",
        json={"name": "To Delete"},
        headers=auth_headers,
    )
    pb_id = resp.json()["playbook"]["id"]

    response = await client.delete(f"/api/v1/strategies/playbooks/{pb_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify deleted
    get_resp = await client.get(f"/api/v1/strategies/playbooks/{pb_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_playbook_isolation_between_users(client: AsyncClient, auth_headers: dict):
    """User A cannot access User B's playbooks."""
    # Create playbook as User A
    resp = await client.post(
        "/api/v1/strategies/playbooks",
        json={"name": "User A Playbook"},
        headers=auth_headers,
    )
    pb_id = resp.json()["playbook"]["id"]

    # Register + login User B
    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb_strat@example.com", "password": "Password123!"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "userb_strat@example.com", "password": "Password123!"},
    )
    token_b = login_resp.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    response = await client.get(f"/api/v1/strategies/playbooks/{pb_id}", headers=headers_b)
    assert response.status_code == 404


# ─── Strategy CRUD ─────────────────────────────────────────────────────────────

async def _create_playbook(client: AsyncClient, headers: dict, name: str = "Test PB") -> str:
    resp = await client.post(
        "/api/v1/strategies/playbooks",
        json={"name": name},
        headers=headers,
    )
    return resp.json()["playbook"]["id"]


@pytest.mark.asyncio
async def test_create_strategy(client: AsyncClient, auth_headers: dict):
    pb_id = await _create_playbook(client, auth_headers)
    payload = {
        "name": "Breakout Scanner",
        "automation_mode": "semi_auto",
        "watchlist": ["AAPL", "SPY", "QQQ"],
        "config": {"min_volume": 1000000, "min_range_bars": 5},
    }
    response = await client.post(
        f"/api/v1/strategies/playbooks/{pb_id}/strategies",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()["strategy"]
    assert data["name"] == "Breakout Scanner"
    assert data["automation_mode"] == "semi_auto"
    assert data["watchlist"] == ["AAPL", "SPY", "QQQ"]
    assert data["is_active"] is False  # default


@pytest.mark.asyncio
async def test_create_strategy_invalid_automation_mode(client: AsyncClient, auth_headers: dict):
    pb_id = await _create_playbook(client, auth_headers)
    response = await client.post(
        f"/api/v1/strategies/playbooks/{pb_id}/strategies",
        json={"name": "Bad Mode", "automation_mode": "turbo"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "automation_mode" in response.text


@pytest.mark.asyncio
async def test_list_strategies(client: AsyncClient, auth_headers: dict):
    pb_id = await _create_playbook(client, auth_headers)
    await client.post(
        f"/api/v1/strategies/playbooks/{pb_id}/strategies",
        json={"name": "S1"},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/strategies/playbooks/{pb_id}/strategies",
        json={"name": "S2"},
        headers=auth_headers,
    )
    response = await client.get(
        f"/api/v1/strategies/playbooks/{pb_id}/strategies",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()["strategies"]) == 2


@pytest.mark.asyncio
async def test_update_strategy_automation_mode(client: AsyncClient, auth_headers: dict):
    pb_id = await _create_playbook(client, auth_headers)
    resp = await client.post(
        f"/api/v1/strategies/playbooks/{pb_id}/strategies",
        json={"name": "Toggle Test"},
        headers=auth_headers,
    )
    strat_id = resp.json()["strategy"]["id"]

    # Toggle to full_auto
    response = await client.put(
        f"/api/v1/strategies/strategies/{strat_id}",
        json={"automation_mode": "full_auto", "is_active": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["strategy"]
    assert data["automation_mode"] == "full_auto"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_delete_strategy(client: AsyncClient, auth_headers: dict):
    pb_id = await _create_playbook(client, auth_headers)
    resp = await client.post(
        f"/api/v1/strategies/playbooks/{pb_id}/strategies",
        json={"name": "Del Strat"},
        headers=auth_headers,
    )
    strat_id = resp.json()["strategy"]["id"]

    response = await client.delete(
        f"/api/v1/strategies/strategies/{strat_id}",
        headers=auth_headers,
    )
    assert response.status_code == 204

    # Verify deleted
    get_resp = await client.get(
        f"/api/v1/strategies/strategies/{strat_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 404


# ─── Pattern detectors (unit tests) ───────────────────────────────────────────

def test_pin_bar_bullish():
    from app.strategies.patterns.pin_bar import detect_pin_bar
    # Hammer: open ~= close near high, long lower wick
    opens  = [Decimal("100")]
    highs  = [Decimal("101")]
    lows   = [Decimal("95")]
    closes = [Decimal("100.5")]
    r = detect_pin_bar(opens, highs, lows, closes)
    assert r.detected is True
    assert r.direction == "bullish"


def test_pin_bar_bearish():
    from app.strategies.patterns.pin_bar import detect_pin_bar
    # Shooting star: open ~= close near low, long upper wick
    opens  = [Decimal("100")]
    highs  = [Decimal("106")]
    lows   = [Decimal("99.5")]
    closes = [Decimal("100.2")]
    r = detect_pin_bar(opens, highs, lows, closes)
    assert r.detected is True
    assert r.direction == "bearish"


def test_pin_bar_not_detected_normal_candle():
    from app.strategies.patterns.pin_bar import detect_pin_bar
    # Normal candle — no long wick
    opens  = [Decimal("100")]
    highs  = [Decimal("103")]
    lows   = [Decimal("98")]
    closes = [Decimal("102")]
    r = detect_pin_bar(opens, highs, lows, closes)
    assert r.detected is False


def test_breakout_bullish():
    from app.strategies.patterns.breakout import detect_breakout
    n = 25
    # 20 bars consolidating at 100, then a breakout close at 105
    highs  = [Decimal("102")] * n
    lows   = [Decimal("98")] * n
    closes = [Decimal("100")] * (n - 1) + [Decimal("103")]
    r = detect_breakout(highs, lows, closes, lookback=20)
    assert r.detected is True
    assert r.direction == "bullish"


def test_breakout_bearish():
    from app.strategies.patterns.breakout import detect_breakout
    n = 25
    highs  = [Decimal("102")] * n
    lows   = [Decimal("98")] * n
    closes = [Decimal("100")] * (n - 1) + [Decimal("97")]
    r = detect_breakout(highs, lows, closes, lookback=20)
    assert r.detected is True
    assert r.direction == "bearish"


def test_breakout_not_detected_inside_range():
    from app.strategies.patterns.breakout import detect_breakout
    n = 25
    highs  = [Decimal("102")] * n
    lows   = [Decimal("98")] * n
    closes = [Decimal("100")] * n
    r = detect_breakout(highs, lows, closes, lookback=20)
    assert r.detected is False


def test_volume_spike_detected():
    from app.strategies.patterns.volume_spike import detect_volume_spike
    # 20 bars at volume 100, then a spike at 300
    vols = [100] * 20 + [300]
    r = detect_volume_spike(vols, min_spike_ratio=2.0, lookback=20)
    assert r.detected is True
    assert float(r.spike_ratio) >= 2.0


def test_volume_spike_not_detected():
    from app.strategies.patterns.volume_spike import detect_volume_spike
    vols = [100] * 20 + [150]
    r = detect_volume_spike(vols, min_spike_ratio=2.0, lookback=20)
    assert r.detected is False


def test_vwap_bounce_bullish():
    from app.strategies.patterns.vwap_bounce import detect_vwap_bounce
    # Price above VWAP, touches near VWAP with low, closes above VWAP
    # VWAP ~ average typical price; we'll construct a scenario
    n = 10
    # All bars have typical price around 100 → VWAP ≈ 100
    highs  = [Decimal("101")] * n
    lows   = [Decimal("99")] * (n - 1) + [Decimal("99.7")]  # last bar touches near VWAP
    closes = [Decimal("100")] * (n - 1) + [Decimal("100.5")]  # last bar closes above VWAP
    volumes = [1000] * n
    r = detect_vwap_bounce(highs, lows, closes, volumes, proximity_pct=0.005, lookback=n)
    assert r.detected is True
    assert r.direction == "bullish"


def test_flag_bullish_detected():
    from app.strategies.patterns.flags import detect_flag
    # Pole: closes rise from 100 to 108 over 5 bars (+8%)
    # Flag: 10 bars where closes drift down slightly (max 50% retracement = 4 pts)
    pole = [Decimal(str(100 + i * 1.6)) for i in range(6)]    # 100..108
    flag = [Decimal(str(107 - i * 0.2)) for i in range(11)]   # slight pullback
    closes = pole + flag
    highs  = [c + Decimal("0.5") for c in closes]
    lows   = [c - Decimal("0.5") for c in closes]
    r = detect_flag(highs, lows, closes, pole_bars=5, flag_bars=10, min_pole_gain_pct=3.0)
    assert r.detected is True
    assert r.direction == "bullish"


# ─── Pattern detect API endpoint ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pattern_detect_endpoint_pin_bar(client: AsyncClient, auth_headers: dict):
    # Hammer candle
    candles = [{"open": 100, "high": 101, "low": 95, "close": 100.5, "volume": 1000}]
    response = await client.post(
        "/api/v1/strategies/patterns/detect",
        json={"candles": candles, "patterns": ["pin_bar"]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "pin_bar" in response.json()["patterns"]
    assert response.json()["patterns"]["pin_bar"]["detected"] is True


@pytest.mark.asyncio
async def test_pattern_detect_endpoint_empty_candles(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/strategies/patterns/detect",
        json={"candles": [], "patterns": ["pin_bar"]},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pattern_detect_endpoint_requires_auth(client: AsyncClient):
    """Pattern detect endpoint requires authentication."""
    candles = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}]
    response = await client.post(
        "/api/v1/strategies/patterns/detect",
        json={"candles": candles, "patterns": ["pin_bar"]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_pattern_detect_endpoint_rejects_unknown_pattern(client: AsyncClient, auth_headers: dict):
    """Unknown pattern names return 422."""
    candles = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}]
    response = await client.post(
        "/api/v1/strategies/patterns/detect",
        json={"candles": candles, "patterns": ["typo_pattern"]},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "Unknown patterns" in response.text


@pytest.mark.asyncio
async def test_pattern_detect_endpoint_rejects_too_many_candles(client: AsyncClient, auth_headers: dict):
    """Requests with > 1000 candles return 422."""
    candles = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}] * 1001
    response = await client.post(
        "/api/v1/strategies/patterns/detect",
        json={"candles": candles, "patterns": ["pin_bar"]},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pattern_detect_endpoint_rejects_inverted_ohlc(client: AsyncClient, auth_headers: dict):
    """Candles with high < low are rejected with 422."""
    candles = [{"open": 100, "high": 95, "low": 105, "close": 100, "volume": 1000}]
    response = await client.post(
        "/api/v1/strategies/patterns/detect",
        json={"candles": candles, "patterns": ["pin_bar"]},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_strategy_cross_user_isolation(client: AsyncClient, auth_headers: dict):
    """User B cannot access User A's strategies."""
    pb_id = await _create_playbook(client, auth_headers)
    resp = await client.post(
        f"/api/v1/strategies/playbooks/{pb_id}/strategies",
        json={"name": "User A Strategy"},
        headers=auth_headers,
    )
    strat_id = resp.json()["strategy"]["id"]

    # Register + login User B
    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb_strat2@example.com", "password": "Password123!"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "userb_strat2@example.com", "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    response = await client.get(f"/api/v1/strategies/strategies/{strat_id}", headers=headers_b)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_playbook_cascades_strategies(client: AsyncClient, auth_headers: dict):
    """Deleting a playbook removes all its strategies."""
    pb_id = await _create_playbook(client, auth_headers)
    strat_resp = await client.post(
        f"/api/v1/strategies/playbooks/{pb_id}/strategies",
        json={"name": "Cascade Test Strategy"},
        headers=auth_headers,
    )
    strat_id = strat_resp.json()["strategy"]["id"]

    # Delete the playbook
    await client.delete(f"/api/v1/strategies/playbooks/{pb_id}", headers=auth_headers)

    # Strategy should also be gone
    response = await client.get(f"/api/v1/strategies/strategies/{strat_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_playbook_is_active(client: AsyncClient, auth_headers: dict):
    """Playbook is_active can be toggled via PUT."""
    resp = await client.post(
        "/api/v1/strategies/playbooks",
        json={"name": "Toggle Active"},
        headers=auth_headers,
    )
    pb_id = resp.json()["playbook"]["id"]
    assert resp.json()["playbook"]["is_active"] is True

    response = await client.put(
        f"/api/v1/strategies/playbooks/{pb_id}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["playbook"]["is_active"] is False


@pytest.mark.asyncio
async def test_update_playbook_can_clear_field_to_null(client: AsyncClient, auth_headers: dict):
    """PUT with explicit null clears a field (exclude_unset semantics)."""
    resp = await client.post(
        "/api/v1/strategies/playbooks",
        json={"name": "Nullable Test", "theory": "Some theory"},
        headers=auth_headers,
    )
    pb_id = resp.json()["playbook"]["id"]

    # Explicitly clear theory by sending null
    response = await client.put(
        f"/api/v1/strategies/playbooks/{pb_id}",
        json={"theory": None},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["playbook"]["theory"] is None


def test_pin_bar_doji_not_detected():
    """A doji (open == close, body=0) does not crash and returns not-detected."""
    from app.strategies.patterns.pin_bar import detect_pin_bar
    opens  = [Decimal("100")]
    highs  = [Decimal("102")]
    lows   = [Decimal("98")]
    closes = [Decimal("100")]  # doji: open == close
    r = detect_pin_bar(opens, highs, lows, closes)
    assert r.detected is False


def test_vwap_bounce_bearish():
    from app.strategies.patterns.vwap_bounce import detect_vwap_bounce
    # VWAP ≈ 100; last candle's high touches near VWAP, closes below VWAP
    n = 10
    highs  = [Decimal("101")] * (n - 1) + [Decimal("100.2")]  # last bar touches VWAP
    lows   = [Decimal("99")] * n
    closes = [Decimal("100")] * (n - 1) + [Decimal("99.5")]   # closes below VWAP
    volumes = [1000] * n
    r = detect_vwap_bounce(highs, lows, closes, volumes, proximity_pct=0.005, lookback=n)
    assert r.detected is True
    assert r.direction == "bearish"


def test_flag_bearish_detected():
    from app.strategies.patterns.flags import detect_flag
    # Pole: closes fall from 108 to 100 over 5 bars (-7.4%)
    pole = [Decimal(str(108 - i * 1.6)) for i in range(6)]
    # Flag: 10 bars with slight upward drift (retracement <= 50% of pole = 4 pts)
    flag = [Decimal(str(100.2 + i * 0.15)) for i in range(11)]
    closes = pole + flag
    highs  = [c + Decimal("0.5") for c in closes]
    lows   = [c - Decimal("0.5") for c in closes]
    r = detect_flag(highs, lows, closes, pole_bars=5, flag_bars=10, min_pole_gain_pct=3.0)
    assert r.detected is True
    assert r.direction == "bearish"
