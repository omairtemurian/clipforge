import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: PhosphorIcon;
  title: string;
  children?: ReactNode;
  /** The one thing to do next (a button or a link). */
  action?: ReactNode;
  className?: string;
}

/** A dashed box that says why a list is empty and offers one clear action. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2 rounded-2xl border border-border bg-card px-6 py-14 text-center shadow-card",
        className,
      )}
    >
      <span className="mb-2 flex size-12 items-center justify-center rounded-2xl bg-muted">
        <Icon className="size-6 text-muted-foreground" aria-hidden />
      </span>
      <p className="text-section">{title}</p>
      {children && (
        <p className="max-w-sm text-body text-muted-foreground">{children}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
