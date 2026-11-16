import { useEffect, useRef, useState } from "react";
import { CaretUpIcon, ScrollIcon } from "@phosphor-icons/react";
import type { LogLine } from "@/hooks/useJobEvents";
import { cn } from "@/lib/utils";
import { cardClass } from "@/lib/surfaces";

function clock(at: number): string {
  return new Date(at).toLocaleTimeString([], { hour12: false });
}

/** A drawer with what the job reports as it runs, newest line last. */
export function LogDrawer({ lines }: { lines: LogLine[] }) {
  const [open, setOpen] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) end.current?.scrollIntoView?.({ block: "nearest" });
  }, [open, lines.length]);

  return (
    <section className={cardClass()}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full cursor-pointer items-center gap-2 rounded-2xl px-4 py-3 text-body font-medium outline-none hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <ScrollIcon className="size-4 text-muted-foreground" aria-hidden />
        Live log
        <CaretUpIcon
          className={cn(
            "ml-auto size-4 text-muted-foreground transition-transform",
            !open && "rotate-180",
          )}
          aria-hidden
        />
      </button>
      {open && (
        <div
          role="log"
          aria-label="Live log"
          className="max-h-48 overflow-y-auto border-t border-border px-4 py-3 font-mono text-caption"
        >
          {lines.length === 0 ? (
            <p className="text-muted-foreground">Waiting for news…</p>
          ) : (
            lines.map((line, index) => (
              <p key={index} className="text-muted-foreground">
                <span className="mr-3 text-foreground/60">
                  {clock(line.at)}
                </span>
                {line.text}
              </p>
            ))
          )}
          <div ref={end} />
        </div>
      )}
    </section>
  );
}
