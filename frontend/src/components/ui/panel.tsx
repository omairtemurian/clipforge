import { CaretDownIcon } from "@phosphor-icons/react";
import { useId, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PanelProps {
  title: string;
  /** Right of the title, e.g. a small action. */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

/**
 * A side panel with a header (title and optional actions) over its body;
 * the body holds the panel's controls or its PanelGroups.
 */
export function Panel({ title, actions, children, className }: PanelProps) {
  return (
    <div data-slot="panel" className={cn("flex flex-col", className)}>
      <header className="flex min-h-9 items-center justify-between gap-3 pb-4">
        <h2 className="text-section">{title}</h2>
        {actions}
      </header>
      <div className="flex flex-col gap-5">{children}</div>
    </div>
  );
}

interface PanelGroupProps {
  title: string;
  /** Lets the header fold the group away. */
  collapsible?: boolean;
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * A titled group of controls inside a Panel, separated by a rule. A
 * collapsible group's header is a button (aria-expanded, Enter/Space
 * toggle) that shows or hides the body.
 */
export function PanelGroup({
  title,
  collapsible = false,
  defaultOpen = true,
  children,
}: PanelGroupProps) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  const shown = !collapsible || open;

  return (
    <section
      data-slot="panel-group"
      aria-label={title}
      className="flex flex-col gap-4 border-t border-border/70 pt-4 first:border-t-0 first:pt-0"
    >
      {collapsible ? (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen(!open)}
          className="-mx-2 flex cursor-pointer items-center justify-between rounded-md px-2 py-1 text-body font-semibold text-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {title}
          <CaretDownIcon
            aria-hidden
            className={cn("size-4 transition-transform", !open && "-rotate-90")}
          />
        </button>
      ) : (
        <h3 className="text-body font-semibold">{title}</h3>
      )}
      <div id={bodyId} hidden={!shown} className="flex flex-col gap-5">
        {children}
      </div>
    </section>
  );
}
