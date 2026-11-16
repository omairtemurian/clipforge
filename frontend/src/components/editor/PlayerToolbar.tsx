import {
  CaretDownIcon,
  CheckIcon,
  CropIcon,
  DeviceMobileIcon,
  FrameCornersIcon,
  ImageIcon,
  RectangleIcon,
  SquareIcon,
  UserFocusIcon,
} from "@phosphor-icons/react";
import { DropdownMenu } from "radix-ui";
import type { ReactNode } from "react";
import type { Aspect } from "@/api/clips";
import type { Framing } from "@/api/types";
import { CLIP_LAYOUTS } from "@/components/layoutOptions";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { cn } from "@/lib/utils";

const ASPECTS: { value: Aspect; label: string; icon: ReactNode }[] = [
  { value: "9:16", label: "Vertical", icon: <DeviceMobileIcon aria-hidden /> },
  { value: "1:1", label: "Square", icon: <SquareIcon aria-hidden /> },
  { value: "4:5", label: "Portrait", icon: <DeviceMobileIcon aria-hidden /> },
  {
    value: "16:9",
    label: "Landscape",
    icon: <RectangleIcon aria-hidden />,
  },
];

const BACKGROUNDS: { value: Framing["background"]; label: string }[] = [
  { value: "blur", label: "Blur" },
  { value: "black", label: "Black" },
];

const CONTROL =
  "inline-flex h-8 items-center whitespace-nowrap gap-1.5 rounded-lg px-2.5 text-body font-medium transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:bg-primary/15 aria-pressed:text-primary-ink [&_svg]:size-4 [&_svg]:shrink-0";
const ITEM =
  "flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-body outline-none data-highlighted:bg-muted [&_svg]:size-4";

interface MenuProps<T extends string> {
  label: string;
  trigger: ReactNode;
  options: { value: T; label: string; icon?: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
}

/** A toolbar button (named label: the value's label) that opens a menu of
 * options, value checked. */
function Menu<T extends string>({
  label,
  trigger,
  options,
  value,
  onChange,
}: MenuProps<T>) {
  const selected = options.find((option) => option.value === value);
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger
        className={CONTROL}
        aria-label={`${label}: ${selected?.label ?? value}`}
      >
        {trigger}
        <CaretDownIcon className="text-muted-foreground" aria-hidden />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={6}
          className="z-50 min-w-40 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover"
        >
          {options.map((option) => (
            <DropdownMenu.Item
              key={option.value}
              className={ITEM}
              onSelect={() => onChange(option.value)}
            >
              {option.icon}
              <span className="flex-1">{option.label}</span>
              {option.value === value && (
                <CheckIcon className="text-primary-ink" aria-label="Selected" />
              )}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

interface PlayerToolbarProps {
  edits: ClipEdits;
  /** The project's aspect, which a clip without its own uses. */
  projectAspect: Aspect;
  /** Whether the crop tool can be on (the scene at the playhead is in the
   * fill layout or shows a facecam; default: the clip is in fill). */
  canCrop?: boolean;
  /** Whether the tracker toggle shows (default: canCrop's default). */
  canTrack?: boolean;
  cropping: boolean;
  onCropping: (cropping: boolean) => void;
}

/**
 * The toolbar over the editor's player: the clip's aspect, its layout
 * (every scene's), for fit the background around the video, the crop tool
 * (fill window or facecam box) and for fill the tracker (the window follows the speaker; off, it stays where the crop
 * tool put it).
 */
export function PlayerToolbar({
  edits,
  projectAspect,
  canCrop,
  canTrack,
  cropping,
  onCropping,
}: PlayerToolbarProps) {
  const { layout, framing } = edits.look;
  const crop = canCrop ?? layout === "fill";
  const track = canTrack ?? layout === "fill";
  const aspect = framing.aspect ?? projectAspect;
  const setFraming = (next: Partial<Framing>) =>
    edits.setLook({ framing: { ...framing, ...next } });
  const current = (options: { value: string; icon?: ReactNode }[], v: string) =>
    options.find((option) => option.value === v)?.icon;

  return (
    <div
      role="toolbar"
      aria-label="Player"
      className="flex max-w-full flex-wrap items-center justify-center gap-1 rounded-xl border border-border bg-card p-1"
    >
      <Menu
        label="Aspect ratio"
        trigger={
          <>
            {current(ASPECTS, aspect) ?? <FrameCornersIcon aria-hidden />}
            {aspect}
          </>
        }
        options={[
          ...ASPECTS.map((option) => ({
            ...option,
            label: `${option.value} ${option.label}`,
          })),
          ...(ASPECTS.some((option) => option.value === aspect)
            ? []
            : [
                {
                  value: aspect,
                  label: `${aspect} Custom`,
                  icon: <FrameCornersIcon aria-hidden />,
                },
              ]),
        ]}
        value={aspect}
        onChange={(next) =>
          setFraming({ aspect: next === projectAspect ? null : next })
        }
      />
      <span className="h-5 w-px bg-border" aria-hidden />
      <Menu
        label="Layout"
        trigger={
          <>
            {current(CLIP_LAYOUTS, layout)}
            Layout:{" "}
            {CLIP_LAYOUTS.find((option) => option.value === layout)?.short}
          </>
        }
        options={CLIP_LAYOUTS}
        value={layout}
        onChange={(next) => edits.setLook({ layout: next })}
      />
      {layout === "fit" && (
        <Menu
          label="Background"
          trigger={
            <>
              <ImageIcon aria-hidden />
              Background:{" "}
              {BACKGROUNDS.find((o) => o.value === framing.background)?.label}
            </>
          }
          options={BACKGROUNDS}
          value={framing.background}
          onChange={(next) => setFraming({ background: next })}
        />
      )}
      {(crop || track) && <span className="h-5 w-px bg-border" aria-hidden />}
      {crop && (
        <button
          type="button"
          aria-pressed={cropping}
          onClick={() => onCropping(!cropping)}
          className={CONTROL}
        >
          <CropIcon aria-hidden />
          Crop
        </button>
      )}
      {track && (
        <button
          type="button"
          aria-pressed={framing.tracker}
          onClick={() => setFraming({ tracker: !framing.tracker })}
          className={cn(CONTROL, !framing.tracker && "text-muted-foreground")}
        >
          <UserFocusIcon aria-hidden />
          Tracker {framing.tracker ? "on" : "off"}
        </button>
      )}
    </div>
  );
}
