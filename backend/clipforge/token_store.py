"""The OAuth token store (SPEC-v2 3.10, 4): tokens live outside the database,
one encrypted file per token_ref (SocialAccount.token_ref, the Drive
import's fixed ref) in data/oauth_tokens.

Each file (<token_ref>.token, mode 0600) is a Fernet token (AES-128-CBC +
HMAC-SHA256, cryptography.fernet) of the Token's JSON. The Fernet key is
derived from the data directory's master key (clipforge.watch.keys, also
mode 0600) for the purpose "oauth-token-store", so no key is stored in a
database row either. Plain JSON files of the first token store
(<token_ref>.json, TASK-66) are encrypted and removed when first read.
Tokens are never logged: Token hides them from its repr, and this module
logs file names only.
"""

import base64
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError

from clipforge import config
from clipforge.oauth_tokens import Token, check_ref
from clipforge.watch.keys import derived_secret

logger = logging.getLogger(__name__)

TOKENS_DIRNAME = "oauth_tokens"
KEY_PURPOSE = "oauth-token-store"
SUFFIX = ".token"
LEGACY_SUFFIX = ".json"


def fernet_for(data_dir: Path, purpose: str = KEY_PURPOSE) -> Fernet:
    """Return the Fernet of data_dir's token store, or of another purpose
    (its key is derived from the data directory's master key, made on first
    use)."""
    secret = bytes.fromhex(derived_secret(purpose, data_dir))
    return Fernet(base64.urlsafe_b64encode(secret))


class TokenStore:
    """Tokens saved encrypted as <folder>/<token_ref>.token, readable by the
    owner only; the key comes from data_dir."""

    def __init__(self, folder: Path, data_dir: Path) -> None:
        self.folder = folder
        self._fernet = fernet_for(data_dir)

    @classmethod
    def from_settings(cls) -> "TokenStore":
        """Return the store in the configured data_dir."""
        data_dir = config.settings.data_dir
        return cls(data_dir / TOKENS_DIRNAME, data_dir)

    def load(self, token_ref: str) -> Token | None:
        """Return the token saved under token_ref, or None (also when its
        file cannot be decrypted or read: the account must connect again)."""
        path = self._path(token_ref)
        try:
            data = self._fernet.decrypt(path.read_bytes())
        except FileNotFoundError:
            return self._load_legacy(token_ref)
        except InvalidToken:
            logger.warning("ignoring the token file %s: cannot decrypt it", path.name)
            return None
        return self._parse(data, path)

    def save(self, token_ref: str, token: Token) -> None:
        """Write token under token_ref (encrypted, atomically, mode 0600)."""
        path = self._path(token_ref)
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self._fernet.encrypt(token.model_dump_json().encode()))
        os.replace(tmp, path)

    def delete(self, token_ref: str) -> None:
        """Forget the token of token_ref (nothing if there is none)."""
        self._path(token_ref).unlink(missing_ok=True)
        self._legacy_path(token_ref).unlink(missing_ok=True)

    def _load_legacy(self, token_ref: str) -> Token | None:
        """Return the plain JSON token of the first store under token_ref,
        saved encrypted (and the plain file removed); None if there is none."""
        path = self._legacy_path(token_ref)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        token = self._parse(data, path)
        if token is not None:
            self.save(token_ref, token)
            logger.info("encrypted the plain token file %s", path.name)
        path.unlink(missing_ok=True)
        return token

    @staticmethod
    def _parse(data: bytes, path: Path) -> Token | None:
        try:
            return Token.model_validate_json(data)
        except ValidationError:
            logger.warning("ignoring the unreadable token file %s", path.name)
            return None

    def _path(self, token_ref: str) -> Path:
        return self.folder / f"{check_ref(token_ref)}{SUFFIX}"

    def _legacy_path(self, token_ref: str) -> Path:
        return self.folder / f"{check_ref(token_ref)}{LEGACY_SUFFIX}"
