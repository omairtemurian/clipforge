import { ClockCounterClockwiseIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAccounts } from "@/api/accounts";
import { usePostHistory } from "@/api/posts";
import { HistoryRow } from "@/components/history/HistoryRow";
import { CALENDAR_PATH } from "@/components/navigation";
import { PageHeader } from "@/components/PageHeader";
import { PostEditor } from "@/components/PostEditor";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { accountsById } from "@/lib/calendar";
import {
  HISTORY_FILTERS,
  HISTORY_PAGE,
  type HistoryFilter,
} from "@/lib/postHistory";
import { cardClass, pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/**
 * The posting history (SPEC-v2 3.10): every post that went out (with the
 * link to the live post), failed or was skipped, newest first, filtered by
 * status. A title opens the post's details (post a skipped one now).
 */
export function PostHistoryPage() {
  const [status, setStatus] = useState<HistoryFilter>("all");
  const [limit, setLimit] = useState(HISTORY_PAGE);
  const [openId, setOpenId] = useState<number | null>(null);
  const history = usePostHistory(status, limit);
  const accounts = useAccounts();
  const byId = accountsById(accounts.data);
  const posts = history.data ?? [];
  const open = posts.find((post) => post.id === openId);

  return (
    <div className="pb-section">
      <PageHeader
        title="Post history"
        description="What went out, what failed and what was skipped, newest first."
        actions={
          <NativeSelect
            aria-label="Status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as HistoryFilter);
              setLimit(HISTORY_PAGE);
            }}
          >
            {HISTORY_FILTERS.map((filter) => (
              <option key={filter.value} value={filter.value}>
                {filter.label}
              </option>
            ))}
          </NativeSelect>
        }
      />
      <div className={cn(pageColumn(), "flex flex-col gap-4")}>
        {history.isError && (
          <p role="alert" className="text-body text-destructive">
            The posting history could not be loaded.
          </p>
        )}
        {history.isPending && <Skeleton className="h-40 rounded-2xl" />}
        {history.isSuccess && posts.length === 0 && (
          <EmptyState
            icon={ClockCounterClockwiseIcon}
            title={
              status === "all" ? "Nothing posted yet" : "No posts like this"
            }
            action={
              <Button variant="outline" asChild>
                <Link to={CALENDAR_PATH}>Open the calendar</Link>
              </Button>
            }
          >
            Published, failed and skipped posts show up here with the links to
            the live posts.
          </EmptyState>
        )}
        {posts.length > 0 && (
          <ul
            aria-label="Posts"
            className={cn(cardClass(), "divide-y divide-border")}
          >
            {posts.map((post) => (
              <HistoryRow
                key={post.id}
                post={post}
                account={
                  post.account_id === null
                    ? undefined
                    : byId.get(post.account_id)
                }
                onOpen={(chosen) => setOpenId(chosen.id)}
              />
            ))}
          </ul>
        )}
        {posts.length === limit && (
          <Button
            variant="outline"
            className="self-center"
            disabled={history.isFetching}
            onClick={() => setLimit(limit + HISTORY_PAGE)}
          >
            Show more
          </Button>
        )}
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
    </div>
  );
}
