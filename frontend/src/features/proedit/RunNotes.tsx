import { cn } from "@/lib/utils";
import { splitNotes } from "./editNotes";
import { KIND_LABELS } from "./laneMath";

/** The label of a kind, or of a composite move ("skull_moment" as "Skull
 * moment"). */
function label(kind: string): string {
  const known = (KIND_LABELS as Record<string, string | undefined>)[kind];
  const words = kind.replaceAll("_", " ");
  return known ?? words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * What the Director's post-processing moved or dropped in a run's plan, and
 * the composite moves it left out (SPEC-v3 3.1/3.4): one line each with the
 * kind, the time in the clip and why. Says so when nothing was touched.
 */
export function RunNotes({ notes }: { notes: string[] }) {
  const { edits } = splitNotes(notes);
  return (
    <section aria-label="Edit notes" className="flex flex-col gap-2">
      <h3 className="text-body font-semibold">Moved or dropped</h3>
      {edits.length === 0 ? (
        <p className="text-body text-muted-foreground">
          Every planned move was kept.
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {edits.map((edit, n) => (
            <li
              key={n}
              className="flex flex-wrap items-baseline gap-x-2 text-body"
            >
              <span
                className={cn(
                  "rounded-md px-1.5 text-caption font-medium",
                  edit.action === "Moved"
                    ? "bg-muted text-foreground"
                    : "bg-destructive/10 text-destructive",
                )}
              >
                {edit.action}
              </span>
              <span className="font-medium">{label(edit.kind)}</span>
              <span className="text-muted-foreground tabular-nums">
                {edit.seconds.toFixed(2)} s
              </span>
              <span className="basis-full text-muted-foreground">
                {edit.reason}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
