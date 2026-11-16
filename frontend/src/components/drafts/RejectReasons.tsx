import type { RejectReason } from "@/api/drafts";
import { Button } from "@/components/ui/button";
import { REJECT_REASONS } from "@/lib/drafts";
import { cn } from "@/lib/utils";

interface RejectReasonsProps {
  title: string;
  reason: RejectReason | null;
  onPick: (reason: RejectReason | null) => void;
  onReject: () => void;
  onCancel: () => void;
  busy: boolean;
}

/** The optional reason chips of a reject (one at most), then "Reject clip"
 * or Cancel; pressing R again rejects too. */
export function RejectReasons({
  title,
  reason,
  onPick,
  onReject,
  onCancel,
  busy,
}: RejectReasonsProps) {
  return (
    <div
      role="group"
      aria-label={`Why reject ${title}?`}
      className="flex flex-col gap-3 rounded-xl border border-border bg-muted/40 p-3"
    >
      <p className="text-caption text-muted-foreground">
        Why? (optional) It helps the autopilot pick better clips. Press R again
        to reject, Esc to cancel.
      </p>
      <div className="flex flex-wrap gap-2">
        {REJECT_REASONS.map((chip) => {
          const pressed = chip.value === reason;
          return (
            <button
              key={chip.value}
              type="button"
              aria-pressed={pressed}
              onClick={() => onPick(pressed ? null : chip.value)}
              className={cn(
                "rounded-full border px-3 py-1 text-caption font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                pressed
                  ? "border-destructive bg-destructive/10 text-destructive"
                  : "border-border bg-card text-muted-foreground hover:text-foreground",
              )}
            >
              {chip.label}
            </button>
          );
        })}
      </div>
      <div className="flex gap-2">
        <Button
          variant="destructive"
          size="sm"
          disabled={busy}
          onClick={onReject}
        >
          Reject clip
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
