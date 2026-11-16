-- 018_v2_social: the connected social accounts and the posts of clips
-- (SPEC-v2 3.10, 4: SocialAccount, Post).
--
-- social_account: one row per connected account; a platform may have
-- several, one per (platform, external_id) (connecting the same account
-- again updates its row). token_ref names the account's token in the
-- encrypted token store (data/oauth_tokens, clipforge.token_store): no
-- token is kept in a row. scopes and restrictions are JSON lists of
-- strings.
--
-- post: one clip posted to one account. payload is the JSON object of the
-- platform's post fields. status is draft, queued, uploading, published,
-- failed or canceled (clipforge.posts checks the moves). Deleting a clip
-- deletes its posts; disconnecting an account keeps its posts' history
-- (account_id becomes NULL) and deleting a thumbnail asset clears it.

CREATE TABLE social_account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    token_ref TEXT NOT NULL UNIQUE,
    scopes TEXT NOT NULL,
    connected_at DATETIME NOT NULL,
    restrictions TEXT NOT NULL,
    UNIQUE (platform, external_id)
);

CREATE TABLE post (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clip (id) ON DELETE CASCADE,
    account_id INTEGER REFERENCES social_account (id) ON DELETE SET NULL,
    platform TEXT NOT NULL,
    payload TEXT NOT NULL,
    thumbnail_asset_id INTEGER REFERENCES asset (id) ON DELETE SET NULL,
    scheduled_at DATETIME,
    status TEXT NOT NULL,
    external_post_id TEXT,
    url TEXT,
    error TEXT,
    attempts INTEGER NOT NULL
);
