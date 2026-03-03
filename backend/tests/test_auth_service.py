"""Unit tests for auth service functions."""
import pytest
from app.auth.service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)


def test_password_hashing():
    password = "mysecretpassword"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)


def test_password_wrong():
    hashed = hash_password("correct")
    assert not verify_password("wrong", hashed)


def test_create_and_decode_token():
    data = {"sub": "user-123"}
    token = create_access_token(data)
    decoded = decode_token(token)
    assert decoded["sub"] == "user-123"
    assert "exp" in decoded


def test_token_contains_expiry():
    import time
    from datetime import timedelta
    token = create_access_token({"sub": "test"}, expires_delta=timedelta(hours=1))
    decoded = decode_token(token)
    assert decoded["exp"] > time.time()
