import {
  CalendarDotsIcon,
  CaretDownIcon,
  PaperPlaneTiltIcon,
  UserCheckIcon,
} from "@phosphor-icons/react";
import { Popover } from "radix-ui";
import { useState } from "react";
import type { Clip } from "@/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { QuickPostSheet } from "./QuickPostSheet";
import { SchedulePostModal } from "./SchedulePostModal";

interface PostButtonProps {
  clip: Clip;
  /** An icon-sized button, for a clip card. */
  compact?: boolean;
  disabled?: boolean;
  /** The tooltip of the main button. */
  title?: string;
}

type Open = "quick" | "choose" | "schedule" | null;

const ITEM =
  "flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm outline-none transition-colors hover:bg-muted focus-visible:bg-muted";
const COMPACT =
  "inline-flex h-8 items-center justify-center text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50";

/**
 * The "Post" split button of a clip: the main click posts in one step
 * (the confirm sheet, then one "Post now" to each platform's default
 * account); the arrow offers "Schedule…" and "Choose accounts…".
 */
export function PostButton({
  clip,
  compact = false,
  disabled = false,
  title = "Post to your default accounts",
}: PostButtonProps) {
  const [open, setOpen] = useState<Open>(null);
  const [menu, setMenu] = useState(false);
  const close = () => setOpen(null);

  function pick(next: Open) {
    setMenu(false);
    setOpen(next);
  }

  return (
    <>
      <div className="inline-flex items-center">
        {compact ? (
          <button
            type="button"
            aria-label="Post clip"
            title={title}
            disabled={disabled}
            onClick={() => setOpen("quick")}
            className={cn(COMPACT, "w-8 rounded-l-lg")}
          >
            <PaperPlaneTiltIcon className="size-4" aria-hidden />
          </button>
        ) : (
          <Button
            variant="outline"
            disabled={disabled}
            title={title}
            onClick={() => setOpen("quick")}
            className="rounded-r-none border-r-0"
          >
            <PaperPlaneTiltIcon aria-hidden />
            Post
          </Button>
        )}
        <Popover.Root open={menu} onOpenChange={setMenu}>
          <Popover.Trigger
            aria-label="More posting options"
            disabled={disabled}
            className={
              compact
                ? cn(COMPACT, "w-5 rounded-r-lg")
                : "inline-flex h-8 w-7 items-center justify-center rounded-r-lg border border-border bg-background text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50"
            }
          >
            <CaretDownIcon className="size-3.5" aria-hidden />
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              align="end"
              sideOffset={6}
              aria-label="Posting options"
              className="z-[60] w-52 rounded-xl border border-border bg-popover p-1.5 text-popover-foreground shadow-popover outline-none"
            >
              <button
                type="button"
                className={ITEM}
                onClick={() => pick("schedule")}
              >
                <CalendarDotsIcon className="size-4" aria-hidden />
                Schedule…
              </button>
              <button
                type="button"
                className={ITEM}
                onClick={() => pick("choose")}
              >
                <UserCheckIcon className="size-4" aria-hidden />
                Choose accounts…
              </button>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      </div>
      {(open === "quick" || open === "choose") && (
        <QuickPostSheet
          clip={clip}
          choose={open === "choose"}
          onClose={close}
        />
      )}
      {open === "schedule" && <SchedulePostModal clip={clip} onClose={close} />}
    </>
  );
}
