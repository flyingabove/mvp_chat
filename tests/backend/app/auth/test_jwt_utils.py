"""Unit tests for JWT encode/decode utilities."""
import time
import pytest
from unittest.mock import patch

from backend.app.auth.jwt_utils import create_token, decode_token


def test_create_and_decode_round_trip():
    token = create_token(user_id="user123", email="test@example.com", name="Test User")
    payload = decode_token(token)
    assert payload["sub"] == "user123"
    assert payload["email"] == "test@example.com"
    assert payload["name"] == "Test User"


def test_token_has_expiry():
    token = create_token(user_id="u1", email="a@b.com", name="A")
    payload = decode_token(token)
    assert "exp" in payload
    assert payload["exp"] > time.time()


def test_expired_token_raises():
    with patch("backend.app.auth.jwt_utils.JWT_EXPIRY_DAYS", -1):
        token = create_token(user_id="u1", email="a@b.com", name="A")
    with pytest.raises(Exception):
        decode_token(token)


def test_tampered_token_raises():
    token = create_token(user_id="u1", email="a@b.com", name="A")
    tampered = token[:-4] + "XXXX"
    with pytest.raises(Exception):
        decode_token(tampered)


def test_invalid_token_raises():
    with pytest.raises(Exception):
        decode_token("not.a.valid.jwt")


def test_different_user_ids_produce_different_tokens():
    t1 = create_token(user_id="user1", email="a@b.com", name="A")
    t2 = create_token(user_id="user2", email="a@b.com", name="A")
    assert t1 != t2
