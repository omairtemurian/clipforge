import type { ReactNode } from "react";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

interface SectionProps {
  title: string;
  description: string;
  children: ReactNode;
}

/** A titled card of related settings. */
export function Section({ title, description, children }: SectionProps) {
  return (
    <section
      aria-label={title}
      className={cn(cardClass(), "flex flex-col gap-6 p-6")}
    >
      <div>
        <h2 className="text-section">{title}</h2>
        <p className="mt-1 text-body text-muted-foreground">{description}</p>
      </div>
      {children}
    </section>
  );
}
