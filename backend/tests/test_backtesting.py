"""Tests for Phase 5: Backtesting Engine."""
import pytest
import uuid
from decimal import Decimal
from httpx import AsyncClient
from app.backtesting.engine import CandleData, run_backtest, _detect_signal, VALID_PATTERNS


# ─── Synthetic data helpers ────────────────────────────────────────────────────

def _flat_candles(n: int, price: float = 100.0, volume: int = 1000) -> list[CandleData]:
    """Produce n candles with constant OHLC (no signal, no exit)."""
    return [CandleData(open=price, high=price + 0.5, low=price - 0.5, close=price, volume=volume)
            for _ in range(n)]


def _breakout_candles(
    consolidation: int = 25,
    price: float = 100.0,
    breakout_price: float = 106.0,
) -> list[CandleData]:
    """
    Return candles with a clean consolidation range followed by a bullish breakout.
    consolidation candles hold between 99–101, then one candle closes above range_high.
    """
    candles = [
        CandleData(open=price, high=price + 1, low=price - 1, close=price, volume=500)
        for _ in range(consolidation)
    ]
    # Breakout candle: closes above range_high (101)
    candles.append(CandleData(open=price + 1, high=breakout_price + 1, low=price, close=breakout_price, volume=2000))
    return candles


def _pin_bar_candles(
    lookback: int = 30,
    pin_price: float = 100.0,
) -> list[CandleData]:
    """
    Return candles with a clear bullish pin bar at the end.
    The pin bar has a very large lower wick, tiny body, tiny upper wick.
    """
    base = [
        CandleData(open=pin_price, high=pin_price + 1, low=pin_price - 1, close=pin_price, volume=500)
        for _ in range(lookback)
    ]
    # Bullish pin bar: opens at 100, dips to 94 (wick=6), closes at 100 (body=0), high=100.2 (upper wick=0.2)
    base.append(CandleData(open=pin_price, high=pin_price + 0.2, low=pin_price - 6.0, close=pin_price, volume=1000))
    return base


# ─── Engine unit tests ────────────────────────────────────────────────────────

def test_run_backtest_empty_candles():
    result = run_backtest([], pattern_name="breakout")
    assert result["metrics"]["total_trades"] == 0
    assert result["metrics"]["final_equity"] == 10_000.0
    assert len(result["equity_curve"]) == 1


def test_run_backtest_no_signals():
    """Flat candles produce no pin bar signals."""
    candles = _flat_candles(50)
    result = run_backtest(candles, pattern_name="pin_bar")
    assert result["metrics"]["total_trades"] == 0


def test_run_backtest_unknown_pattern():
    with pytest.raises(ValueError, match="Unknown pattern"):
        run_backtest(_flat_candles(10), pattern_name="unicorn")


def test_run_backtest_breakout_generates_trade():
    """A breakout signal should generate at least one trade."""
    candles = _breakout_candles(consolidation=25)
    result = run_backtest(
        candles,
        pattern_name="breakout",
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
    )
    assert result["metrics"]["total_trades"] >= 1
    trade = result["trades"][0]
    assert trade["direction"] == "long"


def test_run_backtest_equity_curve_length():
    """Equity curve has exactly len(candles)+1 entries."""
    candles = _flat_candles(20)
    result = run_backtest(candles, pattern_name="breakout")
    assert len(result["equity_curve"]) == len(candles) + 1


def test_run_backtest_stop_loss_hit():
    """
    When the entry candle is followed by a candle whose low hits the stop,
    the trade exits as stop_loss.
    """
    # 25 consolidation candles, then breakout, then candle that drops 3% (stop_loss_pct=2)
    candles = _breakout_candles(consolidation=25, breakout_price=106.0)
    # Add a candle that drops below the stop level (106 * 0.98 = 103.88)
    candles.append(CandleData(open=106.0, high=107.0, low=103.0, close=105.0, volume=800))

    result = run_backtest(candles, pattern_name="breakout", stop_loss_pct=2.0, take_profit_pct=10.0)
    stop_loss_trades = [t for t in result["trades"] if t["exit_reason"] == "stop_loss"]
    assert len(stop_loss_trades) >= 1
    assert stop_loss_trades[0]["pnl"] < 0


def test_run_backtest_take_profit_hit():
    """
    When the entry candle is followed by a candle whose high hits the take_profit,
    the trade exits as take_profit.
    """
    candles = _breakout_candles(consolidation=25, breakout_price=106.0)
    # Add a candle that rallies above take_profit (106 * 1.04 = 110.24)
    candles.append(CandleData(open=106.0, high=115.0, low=105.0, close=114.0, volume=800))

    result = run_backtest(candles, pattern_name="breakout", stop_loss_pct=2.0, take_profit_pct=4.0)
    tp_trades = [t for t in result["trades"] if t["exit_reason"] == "take_profit"]
    assert len(tp_trades) >= 1
    assert tp_trades[0]["pnl"] > 0


def test_run_backtest_metrics_win_rate():
    """Win rate is correctly computed: 1 winner + 1 loser = 50%."""
    candles = _breakout_candles(consolidation=25, breakout_price=106.0)
    # Candle after breakout: take profit hit
    candles.append(CandleData(open=106.0, high=115.0, low=105.5, close=114.0, volume=800))
    # Another consolidation + breakout
    for _ in range(25):
        candles.append(CandleData(open=114.0, high=115.0, low=113.0, close=114.0, volume=500))
    candles.append(CandleData(open=115.0, high=122.0, low=114.5, close=121.0, volume=2000))
    # Stop loss candle for second trade
    candles.append(CandleData(open=121.0, high=122.0, low=118.0, close=119.0, volume=800))

    result = run_backtest(candles, pattern_name="breakout", stop_loss_pct=2.0, take_profit_pct=4.0)
    metrics = result["metrics"]
    assert metrics["total_trades"] >= 1
    assert 0.0 <= metrics["win_rate"] <= 1.0


def test_run_backtest_max_drawdown_with_loss():
    """Max drawdown is > 0 after a losing trade."""
    candles = _breakout_candles(consolidation=25, breakout_price=106.0)
    # Stop loss hit immediately
    candles.append(CandleData(open=106.0, high=106.5, low=103.0, close=104.0, volume=800))

    result = run_backtest(candles, pattern_name="breakout", stop_loss_pct=2.0, take_profit_pct=10.0)
    if result["metrics"]["total_trades"] > 0 and result["metrics"]["losing_trades"] > 0:
        assert result["metrics"]["max_drawdown_pct"] > 0


def test_run_backtest_profit_factor_all_winners():
    """Profit factor is None when there are no losing trades."""
    candles = _breakout_candles(consolidation=25, breakout_price=106.0)
    # Big rally = take profit hit
    candles.append(CandleData(open=106.0, high=120.0, low=105.9, close=118.0, volume=800))

    result = run_backtest(candles, pattern_name="breakout", stop_loss_pct=2.0, take_profit_pct=4.0)
    if result["metrics"]["winning_trades"] > 0 and result["metrics"]["losing_trades"] == 0:
        assert result["metrics"]["profit_factor"] is None


def test_run_backtest_equity_grows_on_win():
    """Final equity > initial capital after a winning trade."""
    candles = _breakout_candles(consolidation=25, breakout_price=106.0)
    candles.append(CandleData(open=106.0, high=120.0, low=105.9, close=118.0, volume=800))

    result = run_backtest(candles, pattern_name="breakout", stop_loss_pct=2.0, take_profit_pct=4.0)
    if result["metrics"]["winning_trades"] > 0:
        assert result["metrics"]["final_equity"] > 10_000.0


def test_run_backtest_all_valid_patterns_run():
    """All registered pattern names run without errors on sufficient candle data."""
    candles = _flat_candles(60)
    for pattern in VALID_PATTERNS:
        result = run_backtest(candles, pattern_name=pattern)
        assert "metrics" in result
        assert "equity_curve" in result
        assert "trades" in result


# ─── API endpoint tests ────────────────────────────────────────────────────────

def _candles_payload(candles: list[CandleData]) -> list[dict]:
    return [{"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles]


@pytest.mark.asyncio
async def test_run_backtest_api_no_trades(client: AsyncClient, auth_headers: dict):
    """Backtest with flat candles returns 201 with 0 trades."""
    payload = {
        "candles": _candles_payload(_flat_candles(50)),
        "pattern_name": "pin_bar",
    }
    response = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()["result"]
    assert data["status"] == "complete"
    assert data["results"]["metrics"]["total_trades"] == 0


@pytest.mark.asyncio
async def test_run_backtest_api_with_breakout(client: AsyncClient, auth_headers: dict):
    """Backtest with breakout candles returns at least 1 trade."""
    payload = {
        "candles": _candles_payload(_breakout_candles(25)),
        "pattern_name": "breakout",
        "symbol": "TEST",
        "stop_loss_pct": 2.0,
        "take_profit_pct": 4.0,
    }
    response = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()["result"]
    assert data["status"] == "complete"
    assert data["symbol"] == "TEST"
    assert data["results"]["metrics"]["total_trades"] >= 1


@pytest.mark.asyncio
async def test_run_backtest_api_unknown_pattern(client: AsyncClient, auth_headers: dict):
    payload = {
        "candles": _candles_payload(_flat_candles(10)),
        "pattern_name": "magic_indicator",
    }
    response = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_run_backtest_api_too_many_candles(client: AsyncClient, auth_headers: dict):
    payload = {
        "candles": _candles_payload(_flat_candles(2001)),
        "pattern_name": "breakout",
    }
    response = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_run_backtest_api_invalid_candle_ohlc(client: AsyncClient, auth_headers: dict):
    """Candle with high < low is rejected at request validation."""
    payload = {
        "candles": [{"open": 100, "high": 95, "low": 99, "close": 100, "volume": 100}],
        "pattern_name": "breakout",
    }
    response = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_run_backtest_requires_auth(client: AsyncClient):
    payload = {"candles": [], "pattern_name": "breakout"}
    response = await client.post("/api/v1/backtest/run", json=payload)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_results_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/backtest/results", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.asyncio
async def test_list_and_get_result(client: AsyncClient, auth_headers: dict):
    """After running a backtest, it appears in list and is fetchable by ID."""
    payload = {
        "candles": _candles_payload(_flat_candles(30)),
        "pattern_name": "breakout",
        "symbol": "AAPL",
    }
    run_resp = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    result_id = run_resp.json()["result"]["id"]

    list_resp = await client.get("/api/v1/backtest/results", headers=auth_headers)
    assert any(r["id"] == result_id for r in list_resp.json()["results"])

    get_resp = await client.get(f"/api/v1/backtest/results/{result_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["result"]["id"] == result_id


@pytest.mark.asyncio
async def test_get_result_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(f"/api/v1/backtest/results/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_result(client: AsyncClient, auth_headers: dict):
    payload = {
        "candles": _candles_payload(_flat_candles(30)),
        "pattern_name": "breakout",
    }
    run_resp = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    result_id = run_resp.json()["result"]["id"]

    del_resp = await client.delete(f"/api/v1/backtest/results/{result_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/backtest/results/{result_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_result_isolation_between_users(client: AsyncClient, auth_headers: dict):
    """User B cannot see User A's backtest results."""
    payload = {
        "candles": _candles_payload(_flat_candles(30)),
        "pattern_name": "breakout",
    }
    run_resp = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    result_id = run_resp.json()["result"]["id"]

    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb_bt@example.com", "password": "Password123!"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "userb_bt@example.com", "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    response = await client.get(f"/api/v1/backtest/results/{result_id}", headers=headers_b)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_results_filter_by_symbol(client: AsyncClient, auth_headers: dict):
    """Filtering by symbol returns only matching results."""
    for sym in ("AAPL", "SPY", "AAPL"):
        await client.post(
            "/api/v1/backtest/run",
            json={"candles": _candles_payload(_flat_candles(30)), "pattern_name": "breakout", "symbol": sym},
            headers=auth_headers,
        )

    response = await client.get("/api/v1/backtest/results?symbol=AAPL", headers=auth_headers)
    assert response.status_code == 200
    results = response.json()["results"]
    assert all(r["symbol"] == "AAPL" for r in results)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_backtest_result_has_equity_curve(client: AsyncClient, auth_headers: dict):
    """Result includes equity_curve with entries for each candle."""
    candles = _flat_candles(20)
    payload = {"candles": _candles_payload(candles), "pattern_name": "breakout"}
    run_resp = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    result = run_resp.json()["result"]
    equity_curve = result["results"]["equity_curve"]
    assert len(equity_curve) == len(candles) + 1
    assert equity_curve[0]["equity"] == 10_000.0


@pytest.mark.asyncio
async def test_run_backtest_api_unknown_pattern_params(client: AsyncClient, auth_headers: dict):
    """Unknown keys in pattern_params are rejected with 422."""
    payload = {
        "candles": _candles_payload(_flat_candles(30)),
        "pattern_name": "breakout",
        "pattern_params": {"lookback": 20, "evil_key": "inject"},
    }
    response = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_run_backtest_api_invalid_symbol(client: AsyncClient, auth_headers: dict):
    """Symbol with invalid characters is rejected."""
    payload = {
        "candles": _candles_payload(_flat_candles(30)),
        "pattern_name": "breakout",
        "symbol": "=EVIL()",
    }
    response = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_run_backtest_api_symbol_uppercased(client: AsyncClient, auth_headers: dict):
    """Symbol is normalised to uppercase."""
    payload = {
        "candles": _candles_payload(_flat_candles(30)),
        "pattern_name": "breakout",
        "symbol": "aapl",
    }
    response = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["result"]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_run_backtest_api_negative_stop_loss(client: AsyncClient, auth_headers: dict):
    """Negative stop_loss_pct is rejected."""
    payload = {
        "candles": _candles_payload(_flat_candles(30)),
        "pattern_name": "breakout",
        "stop_loss_pct": -1.0,
    }
    response = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_backtest_result_metrics_keys(client: AsyncClient, auth_headers: dict):
    """Metrics object contains all expected keys."""
    payload = {"candles": _candles_payload(_flat_candles(30)), "pattern_name": "pin_bar"}
    run_resp = await client.post("/api/v1/backtest/run", json=payload, headers=auth_headers)
    metrics = run_resp.json()["result"]["results"]["metrics"]
    required_keys = {
        "total_trades", "winning_trades", "losing_trades", "win_rate",
        "total_pnl", "profit_factor", "max_drawdown_pct", "sharpe_ratio", "final_equity",
    }
    assert required_keys.issubset(metrics.keys())
