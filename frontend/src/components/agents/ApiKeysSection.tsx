import { useId, useState, type FormEvent } from "react";
import { PlusIcon, RobotIcon, TrashIcon } from "@phosphor-icons/react";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "@/api/apiKeys";
import type { ApiKey, ApiKeyCreated } from "@/api/types";
import { Section } from "@/components/appsettings/Section";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { lastUsedLabel, RECENT_DAYS, recentlyUsed } from "@/lib/apiKeys";
import { formatDate, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { SecretOnce } from "./SecretOnce";

/** Which agents made a request lately, from the keys' last use. */
function RecentAgents({ keys }: { keys: ApiKey[] }) {
  const recent = recentlyUsed(keys);
  if (recent.length === 0) {
    return (
      <p className="text-body text-muted-foreground">
        No agent connected in the last {RECENT_DAYS} days.
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-body">
      <span className="text-muted-foreground">Connected recently:</span>
      {recent.map((key) => (
        <Pill key={key.id} tone="success">
          <RobotIcon aria-hidden className="size-3" />
          {key.name} · {timeAgo(key.last_used_at ?? "")}
        </Pill>
      ))}
    </div>
  );
}

function KeyRow({ apiKey }: { apiKey: ApiKey }) {
  const [confirming, setConfirming] = useState(false);
  const revoke = useRevokeApiKey();
  return (
    <li className="flex items-center gap-4 py-3 text-body">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{apiKey.name}</p>
        <p className="text-caption text-muted-foreground">
          <code className="font-mono">{apiKey.prefix}…</code> · made{" "}
          {formatDate(apiKey.created_at)} · {lastUsedLabel(apiKey)}
        </p>
      </div>
      {confirming ? (
        <div className="flex items-center gap-2">
          <Button
            variant="destructive"
            size="sm"
            disabled={revoke.isPending}
            onClick={() =>
              revoke.mutate(apiKey.id, {
                onSettled: () => setConfirming(false),
              })
            }
          >
            Revoke {apiKey.name}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setConfirming(false)}
          >
            Keep
          </Button>
        </div>
      ) : (
        <Button
          variant="outline"
          size="sm"
          aria-label={`Revoke ${apiKey.name}`}
          onClick={() => setConfirming(true)}
        >
          <TrashIcon aria-hidden />
          Revoke
        </Button>
      )}
    </li>
  );
}

/** The API keys of agents and scripts: make one (shown once), see when each
 * was last used, revoke. */
export function ApiKeysSection({
  created,
  onCreated,
  onHide,
}: {
  created: ApiKeyCreated | null;
  onCreated: (key: ApiKeyCreated) => void;
  onHide: () => void;
}) {
  const nameId = useId();
  const [name, setName] = useState("");
  const keys = useApiKeys();
  const create = useCreateApiKey();

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(name.trim(), {
      onSuccess: (key) => {
        setName("");
        onCreated(key);
      },
    });
  }

  return (
    <Section
      title="API keys"
      description="One key per agent or script, so you can see who connected and revoke one without the others."
    >
      <form onSubmit={submit} className="flex items-end gap-2">
        <label htmlFor={nameId} className="flex flex-1 flex-col gap-1.5">
          <span className="text-body font-medium">Key name</span>
          <input
            id={nameId}
            value={name}
            maxLength={100}
            placeholder="e.g. Hermes on my Mac"
            onChange={(event) => setName(event.target.value)}
            className={cn(INPUT, "h-9")}
          />
        </label>
        <Button
          type="submit"
          size="lg"
          disabled={!name.trim() || create.isPending}
        >
          <PlusIcon aria-hidden />
          {create.isPending ? "Creating…" : "Create key"}
        </Button>
      </form>
      {created && (
        <SecretOnce
          label={`API key "${created.name}"`}
          secret={created.key}
          onDone={onHide}
        />
      )}
      {keys.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the API keys.
        </p>
      )}
      {keys.data && <RecentAgents keys={keys.data} />}
      {keys.data && keys.data.length > 0 && (
        <ul
          aria-label="API keys"
          className="flex flex-col divide-y divide-border"
        >
          {keys.data.map((key) => (
            <KeyRow key={key.id} apiKey={key} />
          ))}
        </ul>
      )}
    </Section>
  );
}
