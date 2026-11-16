import { ClockIcon } from "@phosphor-icons/react";
import type { DragEvent } from "react";
import type { Post, SocialAccount } from "@/api/types";
import { AccountAvatar } from "@/components/accounts/AccountAvatar";
import { canDrag, postTime, postTitle, timeLabel } from "@/lib/calendar";
import { cn } from "@/lib/utils";
import { PostStatusPill } from "./PostStatusPill";

interface PostCardProps {
  post: Post;
  account: SocialAccount | undefined;
  onOpen: (post: Post) => void;
  onDragStart: (post: Post) => void;
  onDragEnd: () => void;
}

/** One post on the calendar: account avatar with its platform badge, the
 * account name, status pill, local time and one line of the title. Click
 * opens its details; a scheduled post can be dragged to another day. */
export function PostCard({
  post,
  account,
  onOpen,
  onDragStart,
  onDragEnd,
}: PostCardProps) {
  const draggable = canDrag(post);
  const at = postTime(post);
  const title = postTitle(post);

  function start(event: DragEvent) {
    event.dataTransfer.setData("text/plain", String(post.id));
    event.dataTransfer.effectAllowed = "move";
    onDragStart(post);
  }

  return (
    <button
      type="button"
      draggable={draggable}
      onDragStart={draggable ? start : undefined}
      onDragEnd={onDragEnd}
      onClick={() => onOpen(post)}
      data-post-id={post.id}
      title={draggable ? "Drag to another day to reschedule" : undefined}
      className={cn(
        "flex w-full min-w-0 flex-col gap-1.5 rounded-xl border border-border bg-card p-2.5 text-left shadow-card transition-shadow outline-none hover:shadow-card-hover focus-visible:ring-3 focus-visible:ring-ring/50",
        draggable && "cursor-grab active:cursor-grabbing",
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <AccountAvatar
          account={account}
          platform={post.platform}
          size="sm"
          badge
        />
        <PostStatusPill status={post.status} />
      </span>
      <span className="truncate text-caption font-medium">
        {account?.display_name ?? "Disconnected account"}
      </span>
      {at && (
        <span className="flex items-center gap-1.5 text-caption tabular-nums">
          <ClockIcon aria-hidden className="size-3.5" />
          {timeLabel(at)}
        </span>
      )}
      <span className="truncate text-caption text-muted-foreground">
        {title}
      </span>
    </button>
  );
}
