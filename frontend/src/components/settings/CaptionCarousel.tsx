import { useRef, type ReactNode } from "react";
import {
  CaretLeftIcon,
  CaretRightIcon,
  CheckIcon,
  SubtitlesSlashIcon,
} from "@phosphor-icons/react";
import type { CaptionTemplateInfo } from "@/api/types";
import { Button } from "@/components/ui/button";
import { templateLabel } from "@/lib/processingSettings";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

interface CaptionCarouselProps {
  templates: CaptionTemplateInfo[] | undefined;
  value: string;
  onChange: (name: string) => void;
  /** "row" scrolls sideways with arrows; "grid" wraps every tile. */
  layout?: "row" | "grid";
  /** With onCaptionsOff, a first "No captions" tile; true when chosen. */
  captionsOff?: boolean;
  onCaptionsOff?: () => void;
}

const SKELETONS = 6;

interface TileProps {
  label: string;
  chosen: boolean;
  onClick: () => void;
  className: string;
  children: ReactNode;
}

/** One 9:16 tile of the radio group: its picture and name. */
function Tile({ label, chosen, onClick, className, children }: TileProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={chosen}
      aria-label={label}
      onClick={onClick}
      className={cn(className, "group flex flex-col gap-1.5 outline-none")}
    >
      <span
        className={cn(
          "relative block aspect-[9/16] overflow-hidden rounded-lg border-2 bg-muted transition-colors group-focus-visible:ring-3 group-focus-visible:ring-ring/50",
          chosen
            ? "border-primary"
            : "border-transparent group-hover:border-border",
        )}
      >
        {children}
        {chosen && (
          <span className="absolute top-1.5 right-1.5 flex size-5 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <CheckIcon className="size-3" aria-hidden />
          </span>
        )}
      </span>
      <span
        className={cn(
          "truncate text-caption",
          chosen ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {label}
      </span>
    </button>
  );
}

/** The caption templates as 9:16 preview tiles, in a row or a grid. */
export function CaptionCarousel({
  templates,
  value,
  onChange,
  layout = "row",
  captionsOff = false,
  onCaptionsOff,
}: CaptionCarouselProps) {
  const row = useRef<HTMLDivElement>(null);
  const grid = layout === "grid";
  const tile = grid ? "min-w-0" : "w-28 shrink-0";
  const scroll = (direction: 1 | -1) =>
    row.current?.scrollBy({
      left: direction * row.current.clientWidth * 0.8,
      behavior: "smooth",
    });

  return (
    <div className="relative">
      <div
        ref={row}
        role="radiogroup"
        aria-label="Caption template"
        className={cn(
          "px-1 pt-1 pb-2",
          grid
            ? "grid grid-cols-[repeat(auto-fill,minmax(5.5rem,1fr))] gap-3"
            : "flex gap-3 overflow-x-auto scroll-smooth [scrollbar-width:thin]",
        )}
      >
        {onCaptionsOff && (
          <Tile
            label="No captions"
            chosen={captionsOff}
            onClick={onCaptionsOff}
            className={tile}
          >
            <span className="flex size-full items-center justify-center text-muted-foreground">
              <SubtitlesSlashIcon className="size-6" aria-hidden />
            </span>
          </Tile>
        )}
        {templates
          ? templates.map((template) => (
              <Tile
                key={template.name}
                label={templateLabel(template.name)}
                chosen={!captionsOff && template.name === value}
                onClick={() => onChange(template.name)}
                className={tile}
              >
                <img
                  src={template.preview_url}
                  alt=""
                  loading="lazy"
                  className="size-full object-cover"
                />
              </Tile>
            ))
          : Array.from({ length: SKELETONS }, (_, index) => (
              <Skeleton
                key={index}
                data-testid="template-skeleton"
                className={cn(tile, "aspect-[9/16] rounded-lg")}
              />
            ))}
      </div>
      {!grid && (
        <div className="absolute -top-9 right-0 flex gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Previous templates"
            onClick={() => scroll(-1)}
          >
            <CaretLeftIcon aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Next templates"
            onClick={() => scroll(1)}
          >
            <CaretRightIcon aria-hidden />
          </Button>
        </div>
      )}
    </div>
  );
}
