-- 028_v2_always_hashtags: hashtags that every post to an account carries.
--
-- always_hashtags is a JSON list of hashtags without "#" that a generated
-- post text on the account always includes, besides the global setting and
-- the campaign's required hashtags (steering, owner request 2026-11-02).

ALTER TABLE social_account ADD COLUMN always_hashtags TEXT NOT NULL DEFAULT '[]';
