import { useEffect, useRef, useState } from "react";
import { fetchPostCopy, type RewriteOptions } from "@/api/postCopy";
import type { Clip, SocialAccount } from "@/api/types";
import { currentCopy, withCopy } from "@/lib/postCopy";
import {
  accountFor,
  draftsOf,
  type PostDrafts,
  type PostFields,
  type PostPlatform,
} from "@/lib/postForm";

/**
 * The texts of the "Schedule post" form. On opening, the AI writes each
 * platform of the connected accounts from the clip (a platform the user
 * already typed in keeps their text); `rewrite` writes the current
 * platform's text again with options. A failure leaves the clip's own text
 * and shows `failed`. The AI also adds the always-included hashtags (the
 * setting, the campaign's and those of the platform's default account among
 * `accounts`); the user can still delete them by hand.
 */
export function usePostDrafts(
  clip: Clip,
  platforms: PostPlatform[],
  accounts: SocialAccount[],
) {
  const [drafts, setDrafts] = useState<PostDrafts>(() => draftsOf(clip));
  const [writing, setWriting] = useState<readonly PostPlatform[]>([]);
  const [failed, setFailed] = useState(false);
  const [rewriting, setRewriting] = useState(false);
  const edited = useRef(new Set<PostPlatform>());
  const started = useRef(new Set<PostPlatform>());
  const key = platforms.join();

  useEffect(() => {
    for (const platform of key ? (key.split(",") as PostPlatform[]) : []) {
      if (started.current.has(platform)) continue;
      started.current.add(platform);
      setWriting((old) => [...old, platform]);
      fetchPostCopy(clip.id, platform, {
        silent: true,
        accountId: accountFor(accounts, platform),
      })
        .then((copy) => {
          if (edited.current.has(platform)) return;
          setDrafts((old) => ({
            ...old,
            [platform]: withCopy(old[platform], copy),
          }));
        })
        .catch(() => setFailed(true))
        .finally(() => setWriting((old) => old.filter((p) => p !== platform)));
    }
  }, [clip.id, key, accounts]);

  function change(platform: PostPlatform, fields: PostFields) {
    edited.current.add(platform);
    setDrafts((old) => ({ ...old, [platform]: fields }));
  }

  async function rewrite(platform: PostPlatform, options: RewriteOptions) {
    setRewriting(true);
    try {
      const copy = await fetchPostCopy(clip.id, platform, {
        ...options,
        current: currentCopy(drafts[platform]),
        accountId: accountFor(accounts, platform),
      });
      edited.current.add(platform);
      setDrafts((old) => ({
        ...old,
        [platform]: withCopy(old[platform], copy),
      }));
    } catch {
      // apiFetch already showed the error toast.
    } finally {
      setRewriting(false);
    }
  }

  return { drafts, change, rewrite, rewriting, failed, writing };
}
