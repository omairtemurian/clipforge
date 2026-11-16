import { useCaptionTemplates } from "@/api/templates";
import { Field } from "@/components/settings/Field";
import { NativeSelect } from "@/components/ui/native-select";
import {
  CREDIT_MAX,
  TEXT_MAX,
  type CampaignDraft,
  type CampaignProblems,
  type Platform,
} from "@/lib/campaignForm";
import { SelectField, TextField } from "./TextField";

const PLATFORMS: { value: Platform; label: string }[] = [
  { value: "youtube", label: "YouTube" },
  { value: "tiktok", label: "TikTok" },
  { value: "instagram", label: "Instagram" },
];

interface RulesFieldsProps {
  draft: CampaignDraft;
  problems: CampaignProblems;
  set: (change: Partial<CampaignDraft>) => void;
}

/**
 * The rules a clip must follow for the campaign: the platforms, the length
 * range, the hashtags, credit line and mentions (pasted), the caption
 * template and the notes. The rule checker tests clips against them.
 */
export function CampaignRulesFields({
  draft,
  problems,
  set,
}: RulesFieldsProps) {
  const templates = useCaptionTemplates().data ?? [];

  function togglePlatform(platform: Platform) {
    set({
      platforms: draft.platforms.includes(platform)
        ? draft.platforms.filter((p) => p !== platform)
        : [...draft.platforms, platform],
    });
  }

  return (
    <fieldset className="flex flex-col gap-4 rounded-xl border border-border p-4">
      <legend className="px-1 text-body font-medium">Clip rules</legend>
      <Field label="Allowed platforms">
        <div role="group" aria-label="Allowed platforms" className="flex gap-4">
          {PLATFORMS.map(({ value, label }) => (
            <label key={value} className="flex items-center gap-2 text-body">
              <input
                type="checkbox"
                checked={draft.platforms.includes(value)}
                onChange={() => togglePlatform(value)}
                className="size-4 accent-primary"
              />
              {label}
            </label>
          ))}
        </div>
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <TextField
          label="Minimum length (s)"
          type="number"
          value={draft.minDuration}
          error={problems.minDuration}
          onChange={(minDuration) => set({ minDuration })}
        />
        <TextField
          label="Maximum length (s)"
          type="number"
          value={draft.maxDuration}
          error={problems.maxDuration}
          onChange={(maxDuration) => set({ maxDuration })}
        />
      </div>
      <TextField
        label="Required hashtags"
        rows={2}
        value={draft.hashtags}
        error={problems.hashtags}
        placeholder="#clips #fyp (paste them, separated by spaces or commas)"
        onChange={(hashtags) => set({ hashtags })}
      />
      <TextField
        label="Required credit line"
        value={draft.creditLine}
        maxLength={CREDIT_MAX}
        placeholder="Clip from … (goes in every description)"
        onChange={(creditLine) => set({ creditLine })}
      />
      <TextField
        label="Required tags and mentions"
        rows={2}
        value={draft.mentions}
        error={problems.mentions}
        placeholder="@creator (paste them, separated by spaces or commas)"
        onChange={(mentions) => set({ mentions })}
      />
      <Field label="Caption template" htmlFor="campaign-caption">
        <NativeSelect
          id="campaign-caption"
          value={draft.captionTemplate}
          onChange={(event) => set({ captionTemplate: event.target.value })}
          block
        >
          <option value="">Keep the project's template</option>
          {templates.map(({ name }) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <TextField
        label="Banned content notes"
        rows={3}
        maxLength={TEXT_MAX}
        value={draft.banned}
        placeholder="Paste what the campaign forbids"
        onChange={(banned) => set({ banned })}
      />
      <TextField
        label="Submission instructions"
        rows={3}
        maxLength={TEXT_MAX}
        value={draft.instructions}
        placeholder="Paste how to submit clips"
        onChange={(instructions) => set({ instructions })}
      />
      <SelectField
        label="Monetization elsewhere"
        value={draft.monetization}
        options={[
          { value: "unknown", label: "Unknown" },
          { value: "yes", label: "Allowed" },
          { value: "no", label: "Not allowed" },
        ]}
        onChange={(monetization) => set({ monetization })}
      />
    </fieldset>
  );
}
