import {
  ArrowsClockwiseIcon,
  CheckCircleIcon,
  CircleDashedIcon,
} from "@phosphor-icons/react";
import { setupUrl, useEngines } from "@/api/engines";
import { Button } from "@/components/ui/button";
import { Section } from "./Section";

/** The optional engines with their install state and version. */
export function EnginesSection() {
  const engines = useEngines();
  return (
    <Section
      title="Engines"
      description="Optional local AI engines. A missing one only turns its feature off."
    >
      {engines.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the engines.
        </p>
      )}
      <ul className="flex flex-col divide-y divide-border">
        {engines.data?.map((engine) => (
          <li
            key={engine.name}
            className="flex items-center justify-between gap-4 py-2 text-body"
          >
            <span className="flex items-center gap-2">
              {engine.installed ? (
                <CheckCircleIcon
                  aria-hidden
                  className="size-4 shrink-0 text-success"
                />
              ) : (
                <CircleDashedIcon
                  aria-hidden
                  className="size-4 shrink-0 text-muted-foreground"
                />
              )}
              {engine.label}
            </span>
            {engine.installed ? (
              <span className="text-muted-foreground">
                Installed{engine.version ? ` ${engine.version}` : ""}
              </span>
            ) : (
              <span className="text-muted-foreground">
                Not installed —{" "}
                <a
                  href={setupUrl(engine)}
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  see setup
                </a>
              </span>
            )}
          </li>
        ))}
      </ul>
      <div>
        <Button
          type="button"
          variant="outline"
          disabled={engines.recheck.isPending}
          onClick={() => engines.recheck.mutate()}
        >
          <ArrowsClockwiseIcon aria-hidden />
          {engines.recheck.isPending ? "Checking…" : "Check again"}
        </Button>
      </div>
    </Section>
  );
}
