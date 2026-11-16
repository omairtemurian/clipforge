import type { ReactNode } from "react";
import { Tabs } from "radix-ui";
import { cn } from "@/lib/utils";

interface Tab<T extends string> {
  value: T;
  label: string;
  content: ReactNode;
}

interface PanelTabsProps<T extends string> {
  /** Accessible name of the tab list. */
  label: string;
  tabs: Tab<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}

/** A pill-shaped tab bar over the content of the chosen tab. */
export function PanelTabs<T extends string>({
  label,
  tabs,
  value,
  onChange,
  className,
}: PanelTabsProps<T>) {
  return (
    <Tabs.Root
      value={value}
      onValueChange={(next) => onChange(next as T)}
      className={cn("flex min-w-0 flex-col gap-4", className)}
    >
      <Tabs.List
        aria-label={label}
        className="inline-flex w-fit rounded-full bg-muted p-1"
      >
        {tabs.map((tab) => (
          <Tabs.Trigger
            key={tab.value}
            value={tab.value}
            className="h-7 rounded-full px-4 text-body text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm"
          >
            {tab.label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {tabs.map((tab) => (
        <Tabs.Content
          key={tab.value}
          value={tab.value}
          className="min-w-0 outline-none"
        >
          {tab.content}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}
