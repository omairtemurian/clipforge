import { CircleNotchIcon } from "@phosphor-icons/react";
import { useState } from "react";
import type { RewriteOptions } from "@/api/postCopy";
import { platformLabel } from "@/lib/platforms";
import {
  type PostDrafts,
  type PostFields,
  type PostPlatform,
} from "@/lib/postForm";
import { RewriteMenu } from "./RewriteMenu";
import { PostFieldsForm } from "./PostFieldsForm";

interface PostTextsProps {
  platforms: PostPlatform[];
  drafts: PostDrafts;
  onChange: (platform: PostPlatform, fields: PostFields) => void;
  /** The cover of the posts, or the clip's thumbnail, if any. */
  thumbnailUrl: string | null;
  /** The platforms the AI is still writing. */
  writing: readonly PostPlatform[];
  /** Whether the AI could not write a platform on opening. */
  failed: boolean;
  rewriting: boolean;
  onRewrite: (platform: PostPlatform, options: RewriteOptions) => void;
}

const TAB =
  "rounded-md px-3 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground aria-selected:bg-muted aria-selected:text-foreground";

/** The modal's right column: a tab per platform of the chosen accounts
 * with what the post says there (title where the platform has one,
 * description or caption, hashtags, who can see it), the cover and "Rewrite
 * with AI" (tone, format, hashtags) for the platform shown. */
export function PostTexts({
  platforms,
  drafts,
  onChange,
  thumbnailUrl,
  writing,
  failed,
  rewriting,
  onRewrite,
}: PostTextsProps) {
  const [picked, setPicked] = useState<PostPlatform | null>(null);
  const [broken, setBroken] = useState(false);
  const platform = picked && platforms.includes(picked) ? picked : platforms[0];

  if (!platform) {
    return (
      <section className="flex min-h-48 items-center justify-center rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        Choose the accounts to post to; each platform gets its own text here.
      </section>
    );
  }
  return (
    <section className="flex min-w-0 flex-col gap-4">
      <div className="flex items-center gap-2">
        <div
          role="tablist"
          aria-label="Platforms"
          className="flex flex-wrap gap-1"
        >
          {platforms.map((each) => (
            <button
              key={each}
              type="button"
              role="tab"
              aria-selected={each === platform}
              onClick={() => setPicked(each)}
              className={TAB}
            >
              {platformLabel(each)}
            </button>
          ))}
        </div>
        <div className="ml-auto">
          <RewriteMenu
            busy={rewriting || writing.includes(platform)}
            onRewrite={(options) => onRewrite(platform, options)}
          />
        </div>
      </div>
      {writing.includes(platform) && (
        <p
          role="status"
          className="flex items-center gap-2 text-xs text-muted-foreground"
        >
          <CircleNotchIcon className="size-3 animate-spin" aria-hidden />
          Writing the {platformLabel(platform)} text with AI…
        </p>
      )}
      {failed && (
        <p role="status" className="text-xs text-muted-foreground">
          The AI could not write some posts; the clip&apos;s own text is shown.
        </p>
      )}
      <div className="flex gap-4">
        <PostFieldsForm
          platform={platform}
          fields={drafts[platform]}
          onChange={(fields) => onChange(platform, fields)}
          idPrefix="post"
        />
        <figure className="w-28 shrink-0">
          <div className="aspect-[9/16] overflow-hidden rounded-lg bg-muted">
            {thumbnailUrl && !broken && (
              <img
                src={thumbnailUrl}
                alt="Thumbnail of the clip"
                onError={() => setBroken(true)}
                className="size-full object-cover"
              />
            )}
          </div>
          <figcaption className="mt-1 text-center text-xs text-muted-foreground">
            Thumbnail
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
