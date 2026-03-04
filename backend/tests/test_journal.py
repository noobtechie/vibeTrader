"""Tests for Phase 4: Trading Journal."""
import pytest
import uuid
from datetime import date
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.trade import Trade
from app.enums import TradeStatus


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_trade(db: AsyncSession, user_id: uuid.UUID, **kwargs) -> Trade:
    """Insert a closed trade directly into the test DB."""
    defaults = dict(
        user_id=user_id,
        symbol="AAPL",
        instrument_type="stock",
        side="long",
        quantity=Decimal("10"),
        entry_price=Decimal("150.00"),
        exit_price=Decimal("160.00"),
        status=TradeStatus.closed.value,
        pnl=Decimal("100.00"),
        commission=Decimal("1.00"),
    )
    defaults.update(kwargs)
    trade = Trade(**defaults)
    db.add(trade)
    await db.flush()
    return trade


async def _get_user_id(client: AsyncClient, headers: dict) -> uuid.UUID:
    resp = await client.get("/api/v1/auth/me", headers=headers)
    return uuid.UUID(resp.json()["id"])


# ─── Journal entry CRUD ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_entries_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/journal/entries", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["entries"] == []


@pytest.mark.asyncio
async def test_create_entry_manual(client: AsyncClient, auth_headers: dict):
    payload = {
        "title": "First Trade Entry",
        "notes": "Great setup, executed cleanly",
        "tags": ["breakout", "AAPL"],
        "context_abbreviation": "T",
        "trigger_abbreviation": "B",
        "confidence_before": 8,
        "execution_quality": 7,
        "followed_playbook": True,
        "lessons_learned": "Waited for confirmation",
    }
    response = await client.post("/api/v1/journal/entries", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()["entry"]
    assert data["title"] == "First Trade Entry"
    assert data["tags"] == ["breakout", "AAPL"]
    assert data["confidence_before"] == 8
    assert data["followed_playbook"] is True


@pytest.mark.asyncio
async def test_create_entry_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/journal/entries", json={"title": "x"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_entry_rating_out_of_range(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/journal/entries",
        json={"confidence_before": 11},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_entry(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/journal/entries",
        json={"title": "Test Get"},
        headers=auth_headers,
    )
    entry_id = resp.json()["entry"]["id"]

    response = await client.get(f"/api/v1/journal/entries/{entry_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["entry"]["id"] == entry_id


@pytest.mark.asyncio
async def test_get_entry_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        f"/api/v1/journal/entries/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_entry(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/journal/entries",
        json={"title": "Original", "notes": "Old notes"},
        headers=auth_headers,
    )
    entry_id = resp.json()["entry"]["id"]

    response = await client.put(
        f"/api/v1/journal/entries/{entry_id}",
        json={"notes": "Updated notes", "lessons_learned": "Stay patient"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["entry"]
    assert data["notes"] == "Updated notes"
    assert data["title"] == "Original"  # unset field unchanged


@pytest.mark.asyncio
async def test_delete_entry(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/journal/entries",
        json={"title": "To Delete"},
        headers=auth_headers,
    )
    entry_id = resp.json()["entry"]["id"]

    response = await client.delete(f"/api/v1/journal/entries/{entry_id}", headers=auth_headers)
    assert response.status_code == 204

    get_resp = await client.get(f"/api/v1/journal/entries/{entry_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_entry_isolation_between_users(client: AsyncClient, auth_headers: dict):
    """User B cannot access User A's journal entries."""
    resp = await client.post(
        "/api/v1/journal/entries",
        json={"title": "Private Entry"},
        headers=auth_headers,
    )
    entry_id = resp.json()["entry"]["id"]

    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb_journal@example.com", "password": "Password123!"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "userb_journal@example.com", "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    response = await client.get(f"/api/v1/journal/entries/{entry_id}", headers=headers_b)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_entry_from_trade(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """Auto-create a journal entry from a trade record."""
    user_id = await _get_user_id(client, auth_headers)
    trade = await _seed_trade(db_session, user_id)

    response = await client.post(
        f"/api/v1/journal/entries/from-trade/{trade.id}",
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()["entry"]
    assert data["trade_id"] == str(trade.id)
    assert "AAPL" in data["title"]


@pytest.mark.asyncio
async def test_filter_entries_by_tag(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/v1/journal/entries",
        json={"title": "Tagged", "tags": ["breakout"]},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/journal/entries",
        json={"title": "Untagged"},
        headers=auth_headers,
    )

    response = await client.get(
        "/api/v1/journal/entries?tag=breakout",
        headers=auth_headers,
    )
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert all("breakout" in e["tags"] for e in entries)
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_filter_entries_by_date_range(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/v1/journal/entries",
        json={"title": "Today", "entry_date": "2024-01-15"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/journal/entries",
        json={"title": "Old", "entry_date": "2023-01-01"},
        headers=auth_headers,
    )

    response = await client.get(
        "/api/v1/journal/entries?from_date=2024-01-01&to_date=2024-12-31",
        headers=auth_headers,
    )
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert all(e["entry_date"] >= "2024-01-01" for e in entries)


# ─── Analytics ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analytics_summary_no_trades(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/journal/analytics/summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_trades"] == 0
    assert data["win_rate"] == 0.0


@pytest.mark.asyncio
async def test_analytics_summary_with_trades(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    user_id = await _get_user_id(client, auth_headers)
    await _seed_trade(db_session, user_id, pnl=Decimal("100"), r_multiple=Decimal("2.0"))
    await _seed_trade(db_session, user_id, pnl=Decimal("-50"), r_multiple=Decimal("-1.0"))
    await _seed_trade(db_session, user_id, pnl=Decimal("75"), r_multiple=Decimal("1.5"))

    response = await client.get("/api/v1/journal/analytics/summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_trades"] == 3
    assert data["winning_trades"] == 2
    assert data["losing_trades"] == 1
    assert abs(data["win_rate"] - 0.6667) < 0.001
    assert data["total_pnl"] == 125.0
    assert data["profit_factor"] is not None
    assert data["avg_r_multiple"] is not None


@pytest.mark.asyncio
async def test_analytics_by_day_of_week(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/journal/analytics/by-day-of-week",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "by_day" in data
    assert len(data["by_day"]) == 7
    assert data["by_day"][0]["day"] == "Monday"


@pytest.mark.asyncio
async def test_analytics_by_time_of_day(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/journal/analytics/by-time-of-day",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "by_hour" in data
    assert len(data["by_hour"]) == 24


@pytest.mark.asyncio
async def test_analytics_by_strategy(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/journal/analytics/by-strategy",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "by_strategy" in response.json()


# ─── CSV Export ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_csv_export_empty(client: AsyncClient, auth_headers: dict):
    """CSV export returns a valid CSV file even with no trades."""
    response = await client.get("/api/v1/journal/export/csv", headers=auth_headers)
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = response.text.strip().split("\n")
    assert len(lines) == 1  # only header row


@pytest.mark.asyncio
async def test_csv_export_with_trades(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    user_id = await _get_user_id(client, auth_headers)
    await _seed_trade(db_session, user_id, symbol="SPY", pnl=Decimal("200"))

    response = await client.get("/api/v1/journal/export/csv", headers=auth_headers)
    assert response.status_code == 200
    lines = response.text.strip().split("\n")
    assert len(lines) == 2  # header + 1 trade
    assert "SPY" in lines[1]


@pytest.mark.asyncio
async def test_csv_injection_prevention(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """CSV export sanitizes formula-starting characters in string fields."""
    user_id = await _get_user_id(client, auth_headers)
    trade = await _seed_trade(db_session, user_id, symbol="AAPL", pnl=Decimal("50"))

    # Create a journal entry with a formula-style title and notes
    await client.post(
        f"/api/v1/journal/entries/from-trade/{trade.id}",
        headers=auth_headers,
    )
    # Update the entry with malicious content
    list_resp = await client.get("/api/v1/journal/entries", headers=auth_headers)
    entry_id = list_resp.json()["entries"][0]["id"]
    await client.put(
        f"/api/v1/journal/entries/{entry_id}",
        json={"title": "=HYPERLINK(evil.com)", "notes": "+malicious"},
        headers=auth_headers,
    )

    response = await client.get("/api/v1/journal/export/csv", headers=auth_headers)
    assert response.status_code == 200
    # The formula is still present but prefixed with ' — spreadsheet won't execute it
    assert "'=HYPERLINK(evil.com)" in response.text
    assert "'+malicious" in response.text


@pytest.mark.asyncio
async def test_from_trade_idempotency(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """Creating a journal entry from the same trade twice returns 409 on the second attempt."""
    user_id = await _get_user_id(client, auth_headers)
    trade = await _seed_trade(db_session, user_id)

    resp1 = await client.post(
        f"/api/v1/journal/entries/from-trade/{trade.id}",
        headers=auth_headers,
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"/api/v1/journal/entries/from-trade/{trade.id}",
        headers=auth_headers,
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_from_trade_cross_user_isolation(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """User B cannot create a journal entry from User A's trade."""
    user_a_id = await _get_user_id(client, auth_headers)
    trade = await _seed_trade(db_session, user_a_id)

    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb_from_trade@example.com", "password": "Password123!"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "userb_from_trade@example.com", "password": "Password123!"},
    )
    headers_b = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    response = await client.post(
        f"/api/v1/journal/entries/from-trade/{trade.id}",
        headers=headers_b,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_entry_rejects_foreign_trade_id(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """Setting trade_id in update to a trade owned by another user returns 404."""
    # Create entry as user A
    resp = await client.post(
        "/api/v1/journal/entries",
        json={"title": "Entry to update"},
        headers=auth_headers,
    )
    entry_id = resp.json()["entry"]["id"]

    # Register user B and seed a trade for them
    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb_trade_update@example.com", "password": "Password123!"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "userb_trade_update@example.com", "password": "Password123!"},
    )
    user_b_id = uuid.UUID(login_resp.json()["user"]["id"] if "user" in login_resp.json() else
                          (await client.get("/api/v1/auth/me",
                                            headers={"Authorization": f"Bearer {login_resp.json()['access_token']}"})).json()["id"])
    trade_b = await _seed_trade(db_session, user_b_id)

    # User A tries to assign user B's trade_id
    response = await client.put(
        f"/api/v1/journal/entries/{entry_id}",
        json={"trade_id": str(trade_b.id)},
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_analytics_by_strategy_with_data(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """by-strategy returns correct per-strategy breakdown."""
    user_id = await _get_user_id(client, auth_headers)
    strategy_id = uuid.uuid4()
    await _seed_trade(db_session, user_id, pnl=Decimal("100"), strategy_id=strategy_id)
    await _seed_trade(db_session, user_id, pnl=Decimal("-30"), strategy_id=strategy_id)
    await _seed_trade(db_session, user_id, pnl=Decimal("60"))  # no strategy

    response = await client.get("/api/v1/journal/analytics/by-strategy", headers=auth_headers)
    assert response.status_code == 200
    rows = response.json()["by_strategy"]
    # Should have 2 rows: the strategy and "no_strategy"
    assert len(rows) == 2
    strat_row = next(r for r in rows if r["strategy_id"] == str(strategy_id))
    assert strat_row["total_trades"] == 2
    assert strat_row["total_pnl"] == 70.0


@pytest.mark.asyncio
async def test_update_entry_rejects_duplicate_trade_id(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """Cannot link two journal entries to the same trade via PUT."""
    user_id = await _get_user_id(client, auth_headers)
    trade = await _seed_trade(db_session, user_id)

    # Create first entry and link it to the trade via from-trade
    resp1 = await client.post(
        f"/api/v1/journal/entries/from-trade/{trade.id}",
        headers=auth_headers,
    )
    assert resp1.status_code == 201

    # Create a second, unlinked entry
    resp2 = await client.post(
        "/api/v1/journal/entries",
        json={"title": "Second entry"},
        headers=auth_headers,
    )
    second_entry_id = resp2.json()["entry"]["id"]

    # Try to link the second entry to the same trade
    response = await client.put(
        f"/api/v1/journal/entries/{second_entry_id}",
        json={"trade_id": str(trade.id)},
        headers=auth_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_entry_null_entry_date_defaults_to_today(
    client: AsyncClient, auth_headers: dict
):
    """Explicit null entry_date falls back to today rather than crashing."""
    response = await client.post(
        "/api/v1/journal/entries",
        json={"title": "Null date test", "entry_date": None},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["entry"]["entry_date"] is not None


@pytest.mark.asyncio
async def test_csv_injection_prevention_in_tag(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """Formula characters in individual tags are sanitised in CSV export."""
    user_id = await _get_user_id(client, auth_headers)
    trade = await _seed_trade(db_session, user_id, symbol="AAPL", pnl=Decimal("50"))

    # Create a journal entry linked to the trade with a formula-style tag
    await client.post(
        "/api/v1/journal/entries",
        json={"title": "Tag injection test", "tags": ["normal", "=EVIL()"], "trade_id": str(trade.id)},
        headers=auth_headers,
    )

    response = await client.get("/api/v1/journal/export/csv", headers=auth_headers)
    # The per-tag sanitised form should appear, not the raw formula at cell start
    assert "'=EVIL()" in response.text


@pytest.mark.asyncio
async def test_list_entries_returns_total_count(client: AsyncClient, auth_headers: dict):
    """list_entries returns both page count and total count."""
    for i in range(3):
        await client.post(
            "/api/v1/journal/entries",
            json={"title": f"Entry {i}"},
            headers=auth_headers,
        )

    response = await client.get(
        "/api/v1/journal/entries?limit=2&offset=0", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["entries"]) == 2   # page size
    assert data["total"] >= 3          # at least 3 total


@pytest.mark.asyncio
async def test_analytics_profit_factor_all_winners(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """Profit factor is None (not division-by-zero error) when all trades are winners."""
    user_id = await _get_user_id(client, auth_headers)
    await _seed_trade(db_session, user_id, pnl=Decimal("100"))
    await _seed_trade(db_session, user_id, pnl=Decimal("50"))

    response = await client.get("/api/v1/journal/analytics/summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_trades"] == 2
    assert data["win_rate"] == 1.0
    assert data["profit_factor"] is None  # no losses → gross_loss == 0
