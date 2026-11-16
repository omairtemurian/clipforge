import type { ReactNode } from "react";
import { setupUrl, useEngines } from "@/api/engines";

interface EngineGateProps {
  /** The engine's `name`, for example "kokoro". */
  engine: string;
  children: ReactNode;
}

/**
 * Shows its children when the optional engine is installed, and "Not
 * installed — see setup" with a link to the README section otherwise, so a
 * feature that needs an engine never fails on a machine without it.
 */
export function EngineGate({ engine, children }: EngineGateProps) {
  const engines = useEngines();
  if (engines.isPending) return null;
  const found = engines.data?.find((item) => item.name === engine);
  if (found?.installed) return <>{children}</>;
  if (!found) {
    return (
      <p role="status" className="text-body text-muted-foreground">
        Could not check whether {engine} is installed.
      </p>
    );
  }
  return (
    <p role="status" className="text-body text-muted-foreground">
      Not installed —{" "}
      <a
        href={setupUrl(found)}
        target="_blank"
        rel="noreferrer"
        className="underline underline-offset-2 hover:text-foreground"
      >
        see setup
      </a>
    </p>
  );
}
