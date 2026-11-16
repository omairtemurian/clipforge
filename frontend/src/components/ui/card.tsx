import type * as React from "react";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** A bordered card surface for a group of content. */
export function Card({
  className,
  interactive = false,
  ...props
}: React.ComponentProps<"div"> & { interactive?: boolean }) {
  return (
    <div
      data-slot="card"
      className={cn(cardClass(interactive), className)}
      {...props}
    />
  );
}
