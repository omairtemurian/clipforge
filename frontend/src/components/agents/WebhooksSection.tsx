import { useId, useState, type FormEvent } from "react";
import { PlusIcon, TrashIcon } from "@phosphor-icons/react";
import type { Webhook, WebhookCreate, WebhookCreated } from "@/api/types";
import {
  useCreateWebhook,
  useDeleteWebhook,
  useWebhooks,
} from "@/api/webhooks";
import { Section } from "@/components/appsettings/Section";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";
import { DOCS_BASE } from "./RestApiSection";
import { SecretOnce } from "./SecretOnce";

type WebhookEvent = Webhook["events"][number];

const EVENTS: { event: WebhookEvent; label: string }[] = [
  { event: "project.completed", label: "Project processed" },
  { event: "clip.rendered", label: "Clip rendered" },
  { event: "post.published", label: "Post published" },
  { event: "post.failed", label: "Post failed" },
];

function WebhookRow({ webhook }: { webhook: Webhook }) {
  const remove = useDeleteWebhook();
  return (
    <li className="flex items-center gap-4 py-3 text-body">
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-caption">{webhook.url}</p>
        <div className="mt-1 flex flex-wrap gap-1">
          {webhook.events.map((event) => (
            <Pill key={event} shape="tag">
              {event}
            </Pill>
          ))}
          {!webhook.enabled && <Pill tone="warning">Paused</Pill>}
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        aria-label={`Delete webhook ${webhook.url}`}
        disabled={remove.isPending}
        onClick={() => remove.mutate(webhook.id)}
      >
        <TrashIcon aria-hidden />
        Delete
      </Button>
    </li>
  );
}

/** Webhooks: ClipForge POSTs the chosen events, signed, to n8n, Zapier or a
 * script. Add one (its secret is shown once), see them, delete one. */
export function WebhooksSection() {
  const urlId = useId();
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<WebhookEvent[]>(
    EVENTS.map(({ event }) => event),
  );
  const [created, setCreated] = useState<WebhookCreated | null>(null);
  const webhooks = useWebhooks();
  const create = useCreateWebhook();

  function toggle(event: WebhookEvent) {
    setEvents((current) =>
      current.includes(event)
        ? current.filter((each) => each !== event)
        : [...current, event],
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate({ url: url.trim(), events } as WebhookCreate, {
      onSuccess: (webhook) => {
        setUrl("");
        setCreated(webhook);
      },
    });
  }

  return (
    <Section
      title="Webhooks"
      description="Tell n8n, Zapier or your own script when something happens. Each request is signed with the webhook's secret (X-ClipForge-Signature)."
    >
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label htmlFor={urlId} className="flex flex-col gap-1.5">
          <span className="text-body font-medium">Webhook URL</span>
          <input
            id={urlId}
            type="url"
            value={url}
            placeholder="http://localhost:5678/webhook/clipforge"
            onChange={(event) => setUrl(event.target.value)}
            className={cn(INPUT, "h-9")}
          />
        </label>
        <fieldset className="flex flex-wrap gap-x-5 gap-y-2">
          <legend className="mb-1.5 text-body font-medium">Events</legend>
          {EVENTS.map(({ event, label }) => (
            <label key={event} className="flex items-center gap-2 text-body">
              <input
                type="checkbox"
                checked={events.includes(event)}
                onChange={() => toggle(event)}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <div>
          <Button
            type="submit"
            disabled={!url.trim() || events.length === 0 || create.isPending}
          >
            <PlusIcon aria-hidden />
            {create.isPending ? "Adding…" : "Add webhook"}
          </Button>
        </div>
      </form>
      {created && (
        <SecretOnce
          label="Webhook secret"
          secret={created.secret}
          onDone={() => setCreated(null)}
        />
      )}
      {webhooks.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the webhooks.
        </p>
      )}
      {webhooks.data && webhooks.data.length > 0 && (
        <ul
          aria-label="Webhooks"
          className="flex flex-col divide-y divide-border"
        >
          {webhooks.data.map((webhook) => (
            <WebhookRow key={webhook.id} webhook={webhook} />
          ))}
        </ul>
      )}
      <p className="text-caption text-muted-foreground">
        How to check the signature and what each event sends:{" "}
        <a
          href={`${DOCS_BASE}/automation.md`}
          target="_blank"
          rel="noreferrer"
          className="text-primary-ink underline-offset-4 hover:underline"
        >
          webhook guide
        </a>
        .
      </p>
    </Section>
  );
}
