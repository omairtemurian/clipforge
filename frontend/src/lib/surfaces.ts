import { cn } from "@/lib/utils";

/** How wide a page is: forms and lists of rows, or grids of cards. */
export type PageWidth = "form" | "wide";

const WIDTH: Record<PageWidth, string> = {
  form: "max-w-form",
  wide: "max-w-wide",
};

/** The centered column of a page, with the page padding. */
export function pageColumn(width: PageWidth = "form"): string {
  return cn("mx-auto w-full px-page", WIDTH[width]);
}

/** The bordered surface of a card; `interactive` adds the hover lift. */
export function cardClass(interactive = false): string {
  return cn(
    "rounded-2xl border border-border bg-card shadow-card",
    interactive &&
      "transition-[border-color,box-shadow] focus-within:border-foreground/15 hover:border-foreground/15 hover:shadow-card-hover",
  );
}

/**
 * The frame of a thumbnail or preview of a card; it brightens its ring while
 * the card (a `group`) is hovered or focused.
 */
export const MEDIA_FRAME =
  "relative overflow-hidden rounded-xl bg-muted ring-1 ring-border transition-[box-shadow] group-focus-within:ring-foreground/25 group-hover:shadow-card-hover group-hover:ring-foreground/25";

/**
 * A selectable card row of a list (campaigns, brand templates, chapters):
 * ember border and tint while chosen, the hover lift otherwise.
 */
export function choiceClass(selected: boolean): string {
  return cn(
    cardClass(!selected),
    "rounded-xl p-3 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
    selected && "border-primary bg-primary/10",
  );
}
