-- 020_v2_api_keys: the API keys of the public REST API /api/v1 (SPEC-v2
-- 2.5, 3.14, 4: ApiKey).
--
-- One row per key the owner made. The key itself is shown once, when it is
-- made, and never stored: key_hash is the SHA-256 hex digest of the key
-- (clipforge.api_keys), prefix its first characters so the owner can tell
-- keys apart. last_used_at is when a request last came with the key (NULL:
-- never). Deleting the row revokes the key. No v1 data changes.

CREATE TABLE api_key (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    last_used_at DATETIME,
    key_hash TEXT NOT NULL UNIQUE
);
