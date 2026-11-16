import { ArrowSquareOutIcon, FilmSlateIcon } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import type { Post, SocialAccount } from "@/api/types";
import { AccountAvatar } from "@/components/accounts/AccountAvatar";
import { PostStatusPill } from "@/components/calendar/PostStatusPill";
import { Button } from "@/components/ui/button";
import { postTitle } from "@/lib/calendar";
import { platformLabel } from "@/lib/platforms";
import { historyWhen } from "@/lib/postHistory";

interface HistoryRowProps {
  post: Post;
  account: SocialAccount | undefined;
  onOpen: (post: Post) => void;
}

/** One finished post: account and platform, title (opens the details),
 * when it went out, its status, why it failed or was skipped, and the
 * links to the live post and the clip. */
export function HistoryRow({ post, account, onOpen }: HistoryRowProps) {
  return (
    <li
      data-post-id={post.id}
      className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3"
    >
      <AccountAvatar account={account} platform={post.platform} badge />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <button
          type="button"
          onClick={() => onOpen(post)}
          className="truncate rounded-md text-left text-body font-medium outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {postTitle(post)}
        </button>
        <span className="truncate text-caption text-muted-foreground">
          {account?.display_name ?? "Disconnected account"} ·{" "}
          {platformLabel(post.platform)} · {historyWhen(post)}
        </span>
        {post.error && post.status !== "published" && (
          <span className="text-caption text-muted-foreground">
            {post.error}
          </span>
        )}
      </div>
      <PostStatusPill status={post.status} />
      <div className="flex items-center gap-2">
        {post.url && (
          <Button variant="outline" size="sm" asChild>
            <a href={post.url} target="_blank" rel="noreferrer">
              <ArrowSquareOutIcon aria-hidden />
              View post
            </a>
          </Button>
        )}
        <Button variant="ghost" size="sm" asChild>
          <Link to={`/clips/${post.clip_id}`}>
            <FilmSlateIcon aria-hidden />
            Open clip
          </Link>
        </Button>
      </div>
    </li>
  );
}
