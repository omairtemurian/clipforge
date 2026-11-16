import type { Post } from "@/api/types";
import { Pill } from "@/components/ui/pill";
import { STATUS_LABELS, STATUS_TONES } from "@/lib/calendar";
import { cn } from "@/lib/utils";

/** A post's status pill with a dot: Posted green, Scheduled neutral,
 * Failed red, Draft ember outline. */
export function PostStatusPill({ status }: { status: Post["status"] }) {
  return (
    <Pill
      tone={STATUS_TONES[status]}
      className={cn(
        status === "draft" && "bg-transparent ring-1 ring-primary ring-inset",
        status === "canceled" && "line-through",
      )}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {STATUS_LABELS[status]}
    </Pill>
  );
}
