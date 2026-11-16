import {
  CaretDownIcon,
  PencilLineIcon,
  TrashIcon,
} from "@phosphor-icons/react";
import { DropdownMenu } from "radix-ui";
import { useLayoutEffect, useRef } from "react";

/** Where "Add caption" puts the selected words. */
export type CaptionTarget = "hook_text" | "title";

interface SelectionToolbarProps {
  onCaption: (target: CaptionTarget) => void;
  onDelete: () => void;
}

const ITEM =
  "flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-body outline-none data-highlighted:bg-muted";
const ACTION =
  "inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-body font-medium transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50";

/**
 * The toolbar that floats under the selected words: "Add caption" uses
 * them as the clip's hook or title, "Delete" cuts them. It sits at the
 * start of the selection, moved left if it would leave the transcript.
 */
export function SelectionToolbar({
  onCaption,
  onDelete,
}: SelectionToolbarProps) {
  const ref = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const toolbar = ref.current;
    const bounds = toolbar?.closest("[data-transcript]");
    if (!toolbar || !bounds) return;
    const overflow =
      toolbar.getBoundingClientRect().right -
      bounds.getBoundingClientRect().right;
    toolbar.style.translate = overflow > 0 ? `${-overflow}px 0` : "";
  });

  return (
    <span className="relative inline-block w-0 align-top">
      <span
        ref={ref}
        role="toolbar"
        aria-label="Selected words"
        onPointerDown={(event) => event.stopPropagation()}
        className="absolute top-8 left-0 z-20 flex items-center gap-1 rounded-xl border border-border bg-popover p-1 leading-normal whitespace-nowrap text-popover-foreground shadow-popover"
      >
        <DropdownMenu.Root modal={false}>
          <DropdownMenu.Trigger className={ACTION}>
            <PencilLineIcon className="size-4" aria-hidden />
            Add caption
            <CaretDownIcon
              className="size-3.5 text-muted-foreground"
              aria-hidden
            />
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="start"
              sideOffset={6}
              className="z-50 min-w-40 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover"
            >
              <DropdownMenu.Item
                className={ITEM}
                onSelect={() => onCaption("hook_text")}
              >
                Use as hook
              </DropdownMenu.Item>
              <DropdownMenu.Item
                className={ITEM}
                onSelect={() => onCaption("title")}
              >
                Use as title
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        <span className="h-5 w-px bg-border" aria-hidden />
        <button type="button" onClick={onDelete} className={ACTION}>
          <TrashIcon className="size-4" aria-hidden />
          Delete
        </button>
      </span>
    </span>
  );
}
