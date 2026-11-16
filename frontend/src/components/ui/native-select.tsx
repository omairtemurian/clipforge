import type * as React from "react";
import { CaretDownIcon } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

/** The look of the text inputs, native selects and textareas. */
export const INPUT =
  "w-full rounded-lg border border-input bg-field px-3 text-sm outline-none transition-colors hover:border-foreground/25 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

/**
 * A native select drawn like the inputs, with its own chevron; `block`
 * makes it fill its form field.
 */
export function NativeSelect({
  className,
  block = false,
  ...props
}: React.ComponentProps<"select"> & { block?: boolean }) {
  return (
    <span className={cn("relative inline-flex", block && "flex w-full")}>
      <select
        data-slot="native-select"
        className={cn(
          INPUT,
          "h-9 w-auto cursor-pointer appearance-none pr-8 text-foreground",
          block && "w-full",
          className,
        )}
        {...props}
      />
      <CaretDownIcon
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-muted-foreground"
      />
    </span>
  );
}
