import { useState, type FormEvent } from "react";
import { PlusIcon } from "@phosphor-icons/react";
import { useAddChannel } from "@/api/autoImport";
import { useProcessingDefaults } from "@/api/sources";
import { Field, INPUT } from "@/components/settings/Field";
import { SourceRightsField } from "@/components/SourceRightsField";
import { Button } from "@/components/ui/button";
import { settingsToSend } from "@/lib/processingSettings";
import type { SourceRights } from "@/lib/sourceRights";
import { cn } from "@/lib/utils";
import { cardClass } from "@/lib/surfaces";

/**
 * Watch a channel: its @handle (looked up with the YouTube Data API), id or
 * youtube.com link, and why the owner may
 * use its videos. The channel starts with the saved default settings; the
 * card's "Edit defaults" changes them. Adding does not import the videos
 * already in the channel's feed.
 */
export function AddChannelForm() {
  const defaults = useProcessingDefaults();
  const add = useAddChannel();
  const [channel, setChannel] = useState("");
  const [rights, setRights] = useState<SourceRights | "">("");
  const [creditLine, setCreditLine] = useState("");
  const ready = channel.trim() !== "" && rights !== "" && defaults.data;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || !rights || add.isPending) return;
    add.mutate(
      {
        channel: channel.trim(),
        settings: settingsToSend(ready),
        source_rights: rights,
        credit_line: creditLine.trim(),
      },
      {
        onSuccess: () => {
          setChannel("");
          setCreditLine("");
        },
      },
    );
  }

  return (
    <form
      onSubmit={submit}
      aria-label="Watch a channel"
      className={cn(cardClass(), "flex flex-col gap-5 p-5")}
    >
      <Field label="YouTube channel" htmlFor="auto-import-channel">
        <input
          id="auto-import-channel"
          type="text"
          value={channel}
          onChange={(event) => setChannel(event.target.value)}
          placeholder="@handle, channel id (UC…) or channel link"
          className={cn(INPUT, "h-9")}
        />
      </Field>
      <SourceRightsField
        rights={rights}
        creditLine={creditLine}
        onRightsChange={setRights}
        onCreditLineChange={setCreditLine}
      />
      <div className="flex items-center justify-between gap-4">
        <p className="text-caption text-muted-foreground">
          New videos become top-priority projects with your saved default
          settings. Videos already on the channel are not imported.
        </p>
        <Button type="submit" disabled={!ready || add.isPending}>
          <PlusIcon aria-hidden />
          Watch channel
        </Button>
      </div>
    </form>
  );
}
