import { ArrowSquareOutIcon } from "@phosphor-icons/react";
import { useAgentSetup } from "@/api/apiKeys";
import { SETUP_DOCS_URL } from "@/api/engines";
import { Section } from "@/components/appsettings/Section";
import { Button } from "@/components/ui/button";
import { KEY_PLACEHOLDER } from "@/lib/mcpSnippets";
import { CopyButton } from "./CopyButton";

export const DOCS_BASE = `${SETUP_DOCS_URL}/blob/main/docs`;

/** The REST API for scripts and tools: its address, how to send the key,
 * a first call, and the interactive docs. */
export function RestApiSection({ apiKey }: { apiKey: string | null }) {
  const setup = useAgentSetup();
  const base = `${setup.data?.api_url ?? ""}/api/v1`;
  const example = `curl -s ${base}/projects -H 'X-API-Key: ${apiKey ?? KEY_PLACEHOLDER}'`;

  return (
    <Section
      title="REST API"
      description="The same operations over HTTP for scripts, n8n or Zapier. Send the key as X-API-Key (or Authorization: Bearer)."
    >
      {setup.data && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <code
              aria-label="API address"
              className="min-w-0 flex-1 rounded-md bg-muted px-3 py-2 font-mono text-caption"
            >
              {base}
            </code>
            <CopyButton text={base} label="Copy API address" />
          </div>
          <div className="flex items-center gap-2">
            <code
              aria-label="Example request"
              className="min-w-0 flex-1 rounded-md bg-muted px-3 py-2 font-mono text-caption break-all"
            >
              {example}
            </code>
            <CopyButton text={example} label="Copy example request" />
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline">
          <a
            href={setup.data?.docs_url ?? "/api/docs"}
            target="_blank"
            rel="noreferrer"
          >
            <ArrowSquareOutIcon aria-hidden />
            Open API docs (/api/docs)
          </a>
        </Button>
        <Button asChild variant="ghost">
          <a
            href={`${DOCS_BASE}/public-api.md`}
            target="_blank"
            rel="noreferrer"
          >
            REST guide
          </a>
        </Button>
        <Button asChild variant="ghost">
          <a href={`${DOCS_BASE}/mcp.md`} target="_blank" rel="noreferrer">
            MCP guide
          </a>
        </Button>
      </div>
    </Section>
  );
}
