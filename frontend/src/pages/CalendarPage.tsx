import { CalendarPlusIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { useAccounts } from "@/api/accounts";
import { usePosts, useUpdatePost } from "@/api/posts";
import type { Post } from "@/api/types";
import { BulkScheduleDialog } from "@/components/BulkScheduleDialog";
import { CalendarGrid } from "@/components/calendar/CalendarGrid";
import { CalendarToolbar } from "@/components/calendar/CalendarToolbar";
import { PageHeader } from "@/components/PageHeader";
import { PostEditor } from "@/components/PostEditor";
import { Button } from "@/components/ui/button";
import {
  NO_FILTERS,
  accountsById,
  dayLabel,
  filterPosts,
  movedTime,
  postTime,
  shiftAnchor,
  timeLabel,
  type CalendarView,
} from "@/lib/calendar";
import { pageColumn } from "@/lib/surfaces";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

/**
 * The posting calendar (SPEC-v2 3.10): every post on its day in a month
 * or week view, filtered by platform, account and status. A click opens
 * the post's details (edit, reschedule, cancel, open clip); a scheduled
 * post dragged to another day is moved there at the same time; "Bulk
 * schedule" posts many clips to many accounts in their free slots.
 */
export function CalendarPage() {
  const [today] = useState(() => new Date());
  const [view, setView] = useState<CalendarView>("month");
  const [anchor, setAnchor] = useState(today);
  const [filters, setFilters] = useState(NO_FILTERS);
  const [openId, setOpenId] = useState<number | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const posts = usePosts();
  const accounts = useAccounts();
  const update = useUpdatePost();
  const byId = accountsById(accounts.data);
  const shown = filterPosts(posts.data ?? [], filters);
  const open = (posts.data ?? []).find((post) => post.id === openId);

  function move(post: Post, day: Date) {
    const at = postTime(post);
    if (!at) return;
    const moment = movedTime(at, day);
    if (moment <= new Date()) {
      toast.error("Pick a day later than now.");
      return;
    }
    update.mutate(
      { id: post.id, patch: { scheduled_at: moment.toISOString() } },
      {
        onSuccess: () =>
          toast.success(`Moved to ${dayLabel(moment)}, ${timeLabel(moment)}.`),
      },
    );
  }

  return (
    <div className="pb-section">
      <PageHeader
        title="Calendar"
        description="Your posts by day. Drag a scheduled post to another day to move it."
        width="wide"
        actions={
          <Button onClick={() => setBulkOpen(true)}>
            <CalendarPlusIcon aria-hidden />
            Bulk schedule
          </Button>
        }
      />
      <div className={cn(pageColumn("wide"), "flex flex-col gap-4")}>
        <CalendarToolbar
          view={view}
          onViewChange={setView}
          anchor={anchor}
          onStep={(step) => setAnchor(shiftAnchor(anchor, view, step))}
          onToday={() => setAnchor(today)}
          filters={filters}
          onFiltersChange={setFilters}
          accounts={accounts.data ?? []}
        />
        {posts.isError && (
          <p role="alert" className="text-body text-destructive">
            The posts could not be loaded.
          </p>
        )}
        <div className="overflow-x-auto">
          <CalendarGrid
            view={view}
            anchor={anchor}
            posts={shown}
            accounts={byId}
            today={today}
            onOpen={(post) => setOpenId(post.id)}
            onMove={move}
          />
        </div>
      </div>
      {open && (
        <PostEditor
          post={open}
          account={
            open.account_id === null ? undefined : byId.get(open.account_id)
          }
          onClose={() => setOpenId(null)}
        />
      )}
      {bulkOpen && <BulkScheduleDialog onClose={() => setBulkOpen(false)} />}
    </div>
  );
}
