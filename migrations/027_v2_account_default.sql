-- 027_v2_account_default: the default account of each platform and the
-- avatar of an account (one-click quick post).
--
-- is_default marks the account that "Post" uses on its platform (one per
-- platform; the API keeps it so). avatar_url is the picture the platform
-- gave at sign-in (NULL: none). Each platform's oldest account becomes its
-- default, so existing owners can quick post at once.

ALTER TABLE social_account ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT 0;

ALTER TABLE social_account ADD COLUMN avatar_url VARCHAR;

UPDATE social_account
SET is_default = 1
WHERE id IN (SELECT MIN(id) FROM social_account GROUP BY platform);
