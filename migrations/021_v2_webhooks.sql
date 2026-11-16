-- 021_v2_webhooks: the webhooks of the automation API and their delivery
-- log (SPEC-v2 3.14, 4: Webhook, WebhookDelivery).
--
-- webhook: one row per endpoint the owner registered. events is a JSON list
-- of the event names it wants. HMAC signing needs the secret itself, so a
-- hash of it would not do: secret_enc is the secret encrypted (Fernet, key
-- derived from the data directory's master key, clipforge.webhooks), never
-- shown again after it is made. enabled off pauses the webhook.
--
-- webhook_delivery: one row per event for one webhook. data is the JSON
-- payload of the event. status is pending (to send, at next_attempt_at),
-- delivered (the endpoint answered 2xx) or failed (gave up after the last
-- attempt). Deleting a webhook deletes its deliveries. No v1 data changes.

CREATE TABLE webhook (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    events TEXT NOT NULL,
    secret_enc TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE webhook_delivery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id INTEGER NOT NULL REFERENCES webhook (id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    data TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    attempted_at DATETIME,
    next_attempt_at DATETIME,
    response_status INTEGER,
    error TEXT
);

CREATE INDEX webhook_delivery_due ON webhook_delivery (status, next_attempt_at);
