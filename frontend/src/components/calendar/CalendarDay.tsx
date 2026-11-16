import { CaretDownIcon, CaretUpIcon } from "@phosphor-icons/react";
import type { DragEvent } from "react";
import type { Post, SocialAccount } from "@/api/types";
import { dayLabel } from "@/lib/calendar";
import { cn } from "@/lib/utils";
import { PostCard } from "./PostCard";

interface CalendarDayProps {
  day: Date;
  posts: Post[];
  accounts: Map<number, SocialAccount>;
  /** Cards shown before "See N more" (null: all). */
  limit: number | null;
  expanded: boolean;
  onToggle: () => void;
  isToday: boolean;
  /** Whether the day is outside the month shown (dimmed). */
  outside: boolean;
  /** Whether a dragged post may be dropped here. */
  dropTarget: boolean;
  onDragOver: (event: DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (event: DragEvent) => void;
  onOpen: (post: Post) => void;
  onDragStart: (post: Post) => void;
  onDragEnd: () => void;
}

/** One day of the calendar: its date top-left (today marked), its posts by
 * time, at most `limit` until the row is expanded, and a drop zone for
 * rescheduling. Empty days stay blank. */
export function CalendarDay({
  day,
  posts,
  accounts,
  limit,
  expanded,
  onToggle,
  isToday,
  outside,
  dropTarget,
  onDragOver,
  onDragLeave,
  onDrop,
  onOpen,
  onDragStart,
  onDragEnd,
}: CalendarDayProps) {
  const label = dayLabel(day);
  const hidden = limit === null ? 0 : Math.max(0, posts.length - limit);
  const shown = expanded || limit === null ? posts : posts.slice(0, limit);

  return (
    <div
      role="gridcell"
      aria-label={isToday ? `${label}, today` : label}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={cn(
        "flex min-h-36 min-w-0 flex-col gap-2 border-r border-b border-border p-2 transition-colors",
        isToday && "bg-primary/5",
        dropTarget && "bg-primary/10 ring-2 ring-primary ring-inset",
      )}
    >
      <span
        className={cn(
          "flex items-center gap-1.5 px-1 text-body",
          outside ? "text-muted-foreground/60" : "text-muted-foreground",
          isToday && "font-semibold text-foreground",
        )}
      >
        {isToday && (
          <span aria-hidden className="size-1.5 rounded-full bg-primary" />
        )}
        {label}
      </span>
      {shown.map((post) => (
        <PostCard
          key={post.id}
          post={post}
          account={
            post.account_id === null ? undefined : accounts.get(post.account_id)
          }
          onOpen={onOpen}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
        />
      ))}
      {hidden > 0 && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={onToggle}
          className="inline-flex items-center justify-center gap-1 self-center rounded-full px-2 py-0.5 text-caption font-medium outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {expanded ? "See less" : `See ${hidden} more`}
          {expanded ? (
            <CaretUpIcon aria-hidden className="size-3" />
          ) : (
            <CaretDownIcon aria-hidden className="size-3" />
          )}
        </button>
      )}
    </div>
  );
}
