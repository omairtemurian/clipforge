import type * as React from "react";
import { cn } from "@/lib/utils";

/** A grey pulsing placeholder shaped like the content that is loading. */
export function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      aria-hidden
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}
