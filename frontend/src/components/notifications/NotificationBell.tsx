import { BellIcon, CheckIcon } from "@phosphor-icons/react";
import { Popover } from "radix-ui";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useMarkAllRead,
  useMarkRead,
  useNotifications,
} from "@/api/notifications";
import type { Notification } from "@/api/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The inbox of the top bar: a bell with the number of unread notifications
 * and a list of the newest ones. A click reads a notification and opens what
 * it is about. */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const notifications = useNotifications();
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();
  const unread = notifications.data?.unread_count ?? 0;
  const items = notifications.data?.items ?? [];

  function openNotification(item: Notification) {
    if (!item.read_at) markRead.mutate(item.id);
    setOpen(false);
    if (item.link) navigate(item.link);
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        className={cn(
          buttonVariants({ variant: "ghost", size: "icon" }),
          "relative justify-self-end",
        )}
        aria-label={
          unread > 0 ? `Notifications, ${unread} unread` : "Notifications"
        }
      >
        <BellIcon aria-hidden />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute -top-0.5 -right-0.5 grid min-w-4 place-items-center rounded-full bg-primary px-1 text-[10px] leading-4 font-semibold text-primary-foreground"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          aria-label="Notifications"
          className="z-50 flex max-h-[28rem] w-96 max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-popover"
        >
          <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
            <h2 className="text-section">Notifications</h2>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={unread === 0 || markAll.isPending}
              onClick={() => markAll.mutate()}
            >
              <CheckIcon aria-hidden />
              Mark all read
            </Button>
          </div>
          {items.length === 0 ? (
            <p className="px-4 py-8 text-center text-body text-muted-foreground">
              Nothing yet. Finished projects, failed renders and posts show up
              here.
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-border overflow-y-auto">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => openNotification(item)}
                    className="flex w-full flex-col gap-0.5 px-4 py-3 text-left transition-colors outline-none hover:bg-muted focus-visible:bg-muted"
                  >
                    <span className="flex items-center gap-2">
                      {!item.read_at && (
                        <span
                          role="img"
                          aria-label="Unread"
                          className="size-2 shrink-0 rounded-full bg-primary"
                        />
                      )}
                      <span
                        className={cn(
                          "text-body",
                          !item.read_at && "font-medium",
                        )}
                      >
                        {item.title}
                      </span>
                    </span>
                    {item.body && (
                      <span className="text-caption text-muted-foreground">
                        {item.body}
                      </span>
                    )}
                    <span className="text-caption text-muted-foreground">
                      {timeAgo(item.created_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
