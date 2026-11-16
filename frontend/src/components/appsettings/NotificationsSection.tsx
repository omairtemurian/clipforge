import { useState } from "react";
import { BellRingingIcon, FloppyDiskIcon } from "@phosphor-icons/react";
import { useSaveAppSettings } from "@/api/appSettings";
import {
  useNotificationChannels,
  useSendTestNotification,
} from "@/api/notifications";
import type { SettingsView } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ToggleRow } from "@/components/ui/toggle-row";
import {
  notifyDirty,
  notifyDraftOf,
  notifyPatch,
  notifyProblems,
  type NotifyDraft,
  type NotifyTextField,
} from "@/lib/notifySettings";
import { toast } from "@/lib/toast";
import { Section } from "./Section";
import { SecretSetting } from "./SecretSetting";
import { TextSetting } from "./TextSetting";

/** Where notifications go besides the bell: email through your own SMTP
 * server, the desktop, and the usage warning. Saved with its own button; the
 * SMTP password is write-only. */
export function NotificationsSection({ saved }: { saved: SettingsView }) {
  const [draft, setDraft] = useState<NotifyDraft>(() => notifyDraftOf(saved));
  const [submitted, setSubmitted] = useState(false);
  const save = useSaveAppSettings((next) => {
    setDraft(notifyDraftOf(next));
    setSubmitted(false);
  });
  const channels = useNotificationChannels();
  const test = useSendTestNotification();

  const patch = notifyPatch(draft, saved);
  const dirty = notifyDirty(draft, saved);
  const problems = submitted ? notifyProblems(draft) : {};

  const text = (field: NotifyTextField) => ({
    value: draft.text[field],
    onChange: (value: string) =>
      setDraft((current) => ({
        ...current,
        text: { ...current.text, [field]: value },
      })),
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (Object.keys(notifyProblems(draft)).length > 0) return;
    save.mutate(patch);
  }

  function sendTest() {
    test.mutate(undefined, {
      onSuccess: () => {
        void channels.refetch();
        toast.info("Test notification sent. Check the bell.");
      },
    });
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Notifications">
      <Section
        title="Notifications"
        description="Finished projects, failed renders, published or failed posts, usage warnings and the daily digest always show in the bell. You can also get them by email and on the desktop."
      >
        <TextSetting
          label="SMTP server"
          hint="Your mail server, e.g. smtp.example.com. Leave blank to turn email off."
          placeholder="Off"
          {...text("smtp_host")}
        />
        <TextSetting
          label="SMTP port"
          hint="465 uses TLS from the start; any other port starts TLS when the server offers it."
          error={problems.smtp_port}
          value={draft.smtp_port}
          onChange={(smtp_port) =>
            setDraft((current) => ({ ...current, smtp_port }))
          }
        />
        <TextSetting
          label="SMTP user"
          placeholder="None"
          {...text("smtp_user")}
        />
        <SecretSetting
          label="SMTP password"
          isSet={saved.smtp_password_set}
          draft={draft.smtp_password}
          onChange={(smtp_password) =>
            setDraft((current) => ({ ...current, smtp_password }))
          }
        />
        <TextSetting
          label="Send from"
          hint="The From address. Blank uses the SMTP user."
          {...text("smtp_from")}
        />
        <TextSetting
          label="Send to"
          hint="Blank sends to the From address."
          {...text("notify_email_to")}
        />
        <ToggleRow
          label="Desktop notifications"
          hint="Also show each notification as a system notification (macOS or Linux)."
          checked={draft.desktop_notifications}
          onCheckedChange={(desktop_notifications) =>
            setDraft((current) => ({ ...current, desktop_notifications }))
          }
        />
        <TextSetting
          label="Warn when a usage cap is this full (%)"
          hint="Once a month per cap, and again when it is used up."
          error={problems.quota_warn_percent}
          value={draft.quota_warn_percent}
          onChange={(quota_warn_percent) =>
            setDraft((current) => ({ ...current, quota_warn_percent }))
          }
        />
        <TextSetting
          label="Daily digest at"
          hint="Once a day from this time (24 hours, e.g. 08:00): drafts waiting, posts today, submissions to do, estimated earnings. Blank turns it off."
          placeholder="Off"
          error={problems.digest_time}
          value={draft.digest_time}
          onChange={(digest_time) =>
            setDraft((current) => ({ ...current, digest_time }))
          }
        />
        {channels.data && (
          <p className="text-caption text-muted-foreground">
            {channels.data.email
              ? `Email goes to ${channels.data.email_to}.`
              : "Email is off."}{" "}
            Desktop notifications are {channels.data.desktop ? "on" : "off"}.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={!dirty || save.isPending}>
            <FloppyDiskIcon aria-hidden />
            {save.isPending ? "Saving…" : "Save notifications"}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={dirty || test.isPending}
            onClick={sendTest}
          >
            <BellRingingIcon aria-hidden />
            {test.isPending ? "Sending…" : "Send a test"}
          </Button>
          {dirty && (
            <span className="text-caption text-muted-foreground">
              Save before sending a test.
            </span>
          )}
        </div>
      </Section>
    </form>
  );
}
