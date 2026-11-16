import { useState } from "react";
import { FloppyDiskIcon } from "@phosphor-icons/react";
import { useSaveAppSettings } from "@/api/appSettings";
import type { SettingsView } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  draftOf,
  settingsPatch,
  validateSettings,
  type KeyDraft,
  type KeyField,
  type LlmProvider,
  type SettingsDraft,
  type TextField,
  type TranscribeBackend,
  type VideoEncoder,
} from "@/lib/settingsForm";
import { DefaultsSection } from "./DefaultsSection";
import { LlmSection } from "./LlmSection";
import { PostingSection } from "./PostingSection";
import { RenderSection } from "./RenderSection";
import { StoragePathsSection } from "./StoragePathsSection";

/**
 * The form of the Settings page. It edits a draft of the saved settings and
 * sends only what changed; typed keys never come back from the server.
 */
export function SettingsForm({ saved }: { saved: SettingsView }) {
  const [draft, setDraft] = useState<SettingsDraft>(() => draftOf(saved));
  const [submitted, setSubmitted] = useState(false);
  const save = useSaveAppSettings(
    (next) => {
      setDraft(draftOf(next));
      setSubmitted(false);
    },
    { verifyLlm: true },
  );

  const patch = settingsPatch(draft, saved);
  const dirty = Object.keys(patch).length > 0;
  const problems = validateSettings(draft);
  const shown = submitted ? problems : {};

  const onText = (field: TextField, value: string) =>
    setDraft((current) => ({
      ...current,
      text: { ...current.text, [field]: value },
    }));
  const onKey = (field: KeyField, key: KeyDraft) =>
    setDraft((current) => ({
      ...current,
      keys: { ...current.keys, [field]: key },
    }));
  const onProvider = (llm_provider: LlmProvider) =>
    setDraft((current) => ({ ...current, llm_provider }));
  const onEncoder = (video_encoder: VideoEncoder) =>
    setDraft((current) => ({ ...current, video_encoder }));
  const onBackend = (transcribe_backend: TranscribeBackend) =>
    setDraft((current) => ({ ...current, transcribe_backend }));

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (Object.keys(problems).length > 0) return;
    save.mutate(patch);
  }

  const common = { draft, problems: shown, onText, onKey };
  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label="Settings"
      className="flex flex-col gap-6"
    >
      <LlmSection {...common} saved={saved} onProvider={onProvider} />
      <RenderSection
        value={draft.video_encoder}
        available={saved.video_encoders}
        onChange={onEncoder}
      />
      <DefaultsSection
        {...common}
        backend={draft.transcribe_backend}
        activeBackend={saved.transcribe_backend_active}
        onBackend={onBackend}
      />
      <StoragePathsSection {...common} dataDir={saved.data_dir} />
      <PostingSection
        value={draft.always_hashtags}
        onChange={(always_hashtags) =>
          setDraft((current) => ({ ...current, always_hashtags }))
        }
        missedPolicy={draft.post_missed_policy}
        onMissedPolicy={(post_missed_policy) =>
          setDraft((current) => ({ ...current, post_missed_policy }))
        }
      />
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!dirty || save.isPending}>
          <FloppyDiskIcon aria-hidden />
          {save.isPending ? "Saving…" : "Save settings"}
        </Button>
        {!dirty && (
          <span className="text-body text-muted-foreground">
            No changes to save.
          </span>
        )}
      </div>
    </form>
  );
}
