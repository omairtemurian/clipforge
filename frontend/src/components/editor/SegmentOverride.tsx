import { LAYOUT_ICONS } from "@/components/layoutOptions";
import {
  SEGMENT_LABELS,
  SEGMENT_OVERRIDES,
  type SceneChoice,
} from "@/lib/scenes";
import { cn } from "@/lib/utils";

interface SegmentOverrideProps {
  /** How the selected segment's scene is framed now. */
  value: SceneChoice;
  onChoose: (choice: SceneChoice) => void;
}

/**
 * The strip's one-click override of the selected segment: Fill, Square,
 * Fit, Split or Track, whatever the auto planning chose for it. Saving the
 * clip stores the choice (PATCH scene_reframes), rendering applies it.
 */
export function SegmentOverride({ value, onChoose }: SegmentOverrideProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Segment layout"
      className="mt-1.5 flex items-center gap-1.5"
    >
      <span className="mr-1 text-caption text-muted-foreground">
        Selected segment
      </span>
      {SEGMENT_OVERRIDES.map((choice) => {
        const chosen = choice === value;
        return (
          <button
            key={choice}
            type="button"
            role="radio"
            aria-checked={chosen}
            onClick={() => onChoose(choice)}
            className={cn(
              "inline-flex h-7 items-center gap-1 rounded-md border px-2 text-caption outline-none focus-visible:ring-2 focus-visible:ring-ring/50 [&_svg]:size-3.5",
              chosen
                ? "border-primary bg-primary/15 text-primary-ink"
                : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {LAYOUT_ICONS[choice]}
            {SEGMENT_LABELS[choice]}
          </button>
        );
      })}
    </div>
  );
}
