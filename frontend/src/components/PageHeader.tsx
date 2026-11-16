import type { ReactNode } from "react";
import { pageColumn, type PageWidth } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  description: string;
  width?: PageWidth;
  /** Buttons on the right of the title. */
  actions?: ReactNode;
}

/** Title and one line of help at the top of a page. */
export function PageHeader({
  title,
  description,
  width = "form",
  actions,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        pageColumn(width),
        "flex items-center justify-between gap-6 pt-section pb-8",
      )}
    >
      <div className="min-w-0">
        <h1 className="text-title">{title}</h1>
        <p className="mt-2 max-w-xl text-body text-muted-foreground">
          {description}
        </p>
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  );
}
