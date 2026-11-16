"""Tests of clipforge.api_keys (keys and their digests) and of the per-key
rate limiter of the public API."""

import hashlib
from datetime import timedelta

from clipforge import api_keys
from clipforge.api.v1.auth import KeyRateLimiter
from schedule_fakes import utc
from sqlalchemy import Engine

T0 = utc(2030, 1, 14, 9)


def test_new_keys_are_random_and_prefixed() -> None:
    keys = {api_keys.new_key() for _ in range(50)}

    assert len(keys) == 50
    assert all(key.startswith("cfk_") and len(key) == 47 for key in keys)


def test_hash_key_is_the_sha256_hex_digest() -> None:
    assert api_keys.hash_key("cfk_x") == hashlib.sha256(b"cfk_x").hexdigest()


def test_authenticate_finds_the_key_and_records_its_use(engine: Engine) -> None:
    created = api_keys.create_key(engine, "agent")

    found = api_keys.authenticate(engine, created.key, T0)
    wrong = api_keys.authenticate(engine, created.key + "x", T0)

    assert found is not None
    assert (found.id, found.name, found.last_used_at) == (created.id, "agent", T0)
    assert wrong is None
    assert api_keys.list_keys(engine) == [found]


def test_the_limiter_admits_per_minute_per_key() -> None:
    limiter = KeyRateLimiter(2)

    admitted = [
        limiter.admit(1, T0),
        limiter.admit(1, T0 + timedelta(seconds=10)),
        limiter.admit(2, T0 + timedelta(seconds=11)),
    ]
    refused = limiter.admit(1, T0 + timedelta(seconds=20))
    later = limiter.admit(1, T0 + timedelta(seconds=60))
    again = limiter.admit(1, T0 + timedelta(seconds=65))

    assert admitted == [None, None, None]
    assert refused == T0 + timedelta(seconds=60)
    assert later is None
    assert again == T0 + timedelta(seconds=70)
