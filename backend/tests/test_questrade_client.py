"""Unit tests for Questrade client token encryption."""
import pytest
from app.brokerage.questrade.auth import encrypt_token, decrypt_token


def test_token_encryption_roundtrip():
    """Encrypting then decrypting should return the original."""
    original = "my-super-secret-api-token-12345"
    encrypted = encrypt_token(original)
    assert encrypted != original
    decrypted = decrypt_token(encrypted)
    assert decrypted == original


def test_different_tokens_produce_different_ciphertext():
    token1 = encrypt_token("token-one")
    token2 = encrypt_token("token-two")
    assert token1 != token2


def test_brokerage_base_interface():
    """BaseBroker should be abstract and uninstantiable."""
    from app.brokerage.base import BaseBroker
    with pytest.raises(TypeError):
        BaseBroker()  # type: ignore
