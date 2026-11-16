import { useState } from "react";
import { useAgentSetup } from "@/api/apiKeys";
import { Section } from "@/components/appsettings/Section";
import { KEY_PLACEHOLDER, mcpClients, type Snippet } from "@/lib/mcpSnippets";
import { CopyButton } from "./CopyButton";

const TAB =
  "rounded-md px-3 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground aria-selected:bg-muted aria-selected:text-foreground";

function SnippetBlock({ snippet }: { snippet: Snippet }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h3 className="text-body font-medium">{snippet.title}</h3>
          <p className="text-caption text-muted-foreground">{snippet.where}</p>
        </div>
        <CopyButton text={snippet.code} label={`Copy ${snippet.title}`} />
      </div>
      <pre
        aria-label={snippet.title}
        className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-caption leading-relaxed whitespace-pre"
      >
        {snippet.code}
      </pre>
    </div>
  );
}

/** Ready-to-copy configs that connect an AI agent (Hermes, Claude, Copilot,
 * any MCP client) to this app through the clipforge-mcp server; the key
 * just made is filled in. */
export function McpSection({ apiKey }: { apiKey: string | null }) {
  const setup = useAgentSetup();
  const [picked, setPicked] = useState("hermes");
  const clients = setup.data
    ? mcpClients(setup.data, apiKey ?? KEY_PLACEHOLDER)
    : [];
  const client = clients.find(({ id }) => id === picked) ?? clients[0];

  return (
    <Section
      title="Connect an AI agent (MCP)"
      description="The clipforge-mcp server gives an agent one tool per API call: projects, clips, renders, post copy and drafts. Keep ClipForge running while the agent works."
    >
      <p className="text-body text-muted-foreground">
        {apiKey ? (
          "Your new key is filled in below."
        ) : (
          <>
            Create a key above to fill it in, or replace{" "}
            <code className="font-mono">{KEY_PLACEHOLDER}</code> with one.
          </>
        )}
      </p>
      {setup.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the MCP setup.
        </p>
      )}
      {client && (
        <>
          <div
            role="tablist"
            aria-label="AI agents"
            className="flex flex-wrap gap-1"
          >
            {clients.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={id === client.id}
                onClick={() => setPicked(id)}
                className={TAB}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            aria-label={client.label}
            className="flex flex-col gap-5"
          >
            {client.snippets.map((snippet) => (
              <SnippetBlock key={snippet.title} snippet={snippet} />
            ))}
          </div>
        </>
      )}
    </Section>
  );
}
