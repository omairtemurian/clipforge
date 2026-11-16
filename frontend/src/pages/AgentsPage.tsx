import { useState } from "react";
import { ShieldCheckIcon } from "@phosphor-icons/react";
import type { ApiKeyCreated } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { ApiKeysSection } from "@/components/agents/ApiKeysSection";
import { McpSection } from "@/components/agents/McpSection";
import { RestApiSection } from "@/components/agents/RestApiSection";
import { WebhooksSection } from "@/components/agents/WebhooksSection";
import { SettingsTabs } from "@/components/appsettings/SettingsTabs";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** Settings -> AI agents & API: API keys (made, shown once, last used,
 * revoked), MCP configs for Hermes, Claude and Copilot, the REST API and
 * webhooks. A key just made fills in the snippets until it is hidden. */
export function AgentsPage() {
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const key = created?.key ?? null;
  return (
    <>
      <PageHeader
        title="AI agents & API"
        description="Connect Hermes, Claude or Copilot over MCP, call the REST API from scripts, and send events to webhooks."
      />
      <div className={cn(pageColumn(), "pb-10")}>
        <div className="flex max-w-2xl flex-col gap-6">
          <SettingsTabs />
          <p className="flex items-center gap-2 rounded-xl bg-muted px-4 py-3 text-body">
            <ShieldCheckIcon
              aria-hidden
              className="size-4 shrink-0 text-primary-ink"
            />
            Agents can make clips and draft posts, but only you can publish or
            queue a post, here in the app.
          </p>
          <ApiKeysSection
            created={created}
            onCreated={setCreated}
            onHide={() => setCreated(null)}
          />
          <McpSection apiKey={key} />
          <RestApiSection apiKey={key} />
          <WebhooksSection />
        </div>
      </div>
    </>
  );
}
