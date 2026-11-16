import type * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const pillVariants = cva(
  "inline-flex items-center gap-1 text-caption font-medium whitespace-nowrap tabular-nums",
  {
    variants: {
      tone: {
        neutral: "bg-muted text-muted-foreground",
        primary: "bg-primary/15 text-primary-ink",
        success: "bg-success/15 text-success",
        warning: "bg-warning/15 text-warning",
        danger: "bg-destructive/15 text-destructive",
        overlay: "bg-overlay text-foreground backdrop-blur-sm",
      },
      shape: {
        pill: "rounded-full px-2 py-0.5",
        tag: "rounded-md px-1.5 py-0.5",
      },
    },
    defaultVariants: { tone: "neutral", shape: "pill" },
  },
);

export type PillTone = NonNullable<VariantProps<typeof pillVariants>["tone"]>;

/**
 * A small status pill or tag (statuses, durations, "Edited"): one look for
 * every badge of the app, colored by its tone.
 */
export function Pill({
  className,
  tone,
  shape,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof pillVariants>) {
  return (
    <span
      data-slot="pill"
      data-tone={tone ?? "neutral"}
      className={cn(pillVariants({ tone, shape }), className)}
      {...props}
    />
  );
}
