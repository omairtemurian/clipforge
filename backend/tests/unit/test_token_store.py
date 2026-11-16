"""Tests for the encrypted OAuth token store (clipforge.token_store): tokens
are kept outside the database in owner-only files that do not show them,
plain files of the first store are encrypted on first read, and a Token
never shows its secrets in a repr or a log."""

import json
import logging
import os
import stat
from pathlib import Path

import pytest
from clipforge.oauth_tokens import Token, new_token_ref
from clipforge.token_store import TokenStore

SECRET_ACCESS = "ya29.secret-access-value"
SECRET_REFRESH = "1//secret-refresh-value"
TOKEN = Token(access_token=SECRET_ACCESS, refresh_token=SECRET_REFRESH, expires_at=5.0)


def store_in(data_dir: Path) -> TokenStore:
    return TokenStore(data_dir / "oauth_tokens", data_dir)


def test_tokens_are_saved_encrypted_in_owner_only_files(tmp_path: Path) -> None:
    store = store_in(tmp_path)
    ref = new_token_ref()
    assert store.load(ref) is None

    store.save(ref, TOKEN)

    path = tmp_path / "oauth_tokens" / f"{ref}.token"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    data = path.read_bytes()
    assert SECRET_ACCESS.encode() not in data
    assert SECRET_REFRESH.encode() not in data
    assert store.load(ref) == TOKEN
    assert store_in(tmp_path).load(ref) == TOKEN
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_store_of_another_data_dir_cannot_read_a_token(tmp_path: Path) -> None:
    store_in(tmp_path / "a").save("me", TOKEN)
    other = TokenStore(tmp_path / "a" / "oauth_tokens", tmp_path / "b")
    assert other.load("me") is None


def test_unreadable_token_files_count_as_no_token(tmp_path: Path) -> None:
    store = store_in(tmp_path)
    store.save("me", TOKEN)
    (tmp_path / "oauth_tokens" / "me.token").write_bytes(b"garbage")
    assert store.load("me") is None
    store.delete("me")
    store.delete("me")
    assert not (tmp_path / "oauth_tokens" / "me.token").exists()
    with pytest.raises(ValueError):
        store.load("a/b")


def test_plain_token_file_of_the_first_store_is_encrypted_on_read(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "oauth_tokens"
    folder.mkdir()
    (folder / "google-drive.json").write_text(json.dumps(TOKEN.model_dump()))
    store = store_in(tmp_path)

    assert store.load("google-drive") == TOKEN

    assert not (folder / "google-drive.json").exists()
    assert SECRET_ACCESS.encode() not in (folder / "google-drive.token").read_bytes()
    assert store.load("google-drive") == TOKEN


def test_token_hides_its_secrets_from_repr_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    logging.getLogger("clipforge").info("token: %s %r", TOKEN, TOKEN)
    for text in (repr(TOKEN), str(TOKEN), caplog.text):
        assert SECRET_ACCESS not in text
        assert SECRET_REFRESH not in text
    assert "expires_at=5.0" in repr(TOKEN)
