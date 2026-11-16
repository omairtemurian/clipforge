import { SCENE_LABELS, type SceneChoice } from "@/lib/scenes";
import { cn } from "@/lib/utils";
import {
  LAYOUT_HINTS,
  LAYOUT_ICONS,
  SCENE_CHOICES,
} from "@/components/layoutOptions";

const TILE =
  "flex min-h-16 flex-col items-center justify-center gap-1 rounded-lg border px-1.5 py-2 text-center text-caption leading-tight transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-5";
const CHOSEN = "border-primary bg-primary/15 text-primary-ink";
const UNCHOSEN =
  "border-border text-muted-foreground hover:bg-muted hover:text-foreground";

interface LayoutPickerProps {
  value: SceneChoice;
  onChange: (choice: SceneChoice) => void;
  /** The choices to offer (default: all of them). */
  choices?: SceneChoice[];
}

/**
 * A grid of tiles, one per way to frame a scene (a radio group named
 * "Layout"): crop to fill (auto, track, fixed) or one of the layouts; the
 * chosen one's hint is under the grid.
 */
export function LayoutPicker({
  value,
  onChange,
  choices = SCENE_CHOICES,
}: LayoutPickerProps) {
  return (
    <div className="flex flex-col gap-2">
      <div
        role="radiogroup"
        aria-label="Layout"
        aria-describedby="layout-picker-hint"
        className="grid grid-cols-3 gap-2"
      >
        {choices.map((choice) => {
          const chosen = choice === value;
          return (
            <button
              key={choice}
              type="button"
              role="radio"
              aria-checked={chosen}
              title={LAYOUT_HINTS[choice]}
              onClick={() => onChange(choice)}
              className={cn(TILE, chosen ? CHOSEN : UNCHOSEN)}
            >
              {LAYOUT_ICONS[choice]}
              {SCENE_LABELS[choice]}
            </button>
          );
        })}
      </div>
      <p id="layout-picker-hint" className="text-caption text-muted-foreground">
        {LAYOUT_HINTS[value]}
      </p>
    </div>
  );
}
