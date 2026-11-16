import { FloppyDiskIcon, WarningIcon } from "@phosphor-icons/react";
import { useState } from "react";
import type { Campaign } from "@/api/types";
import { SelectField } from "@/components/campaigns/TextField";
import { Button } from "@/components/ui/button";
import { ToggleRow } from "@/components/ui/toggle-row";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";
import {
  proEditValues,
  useAutopilotSettings,
  useSaveCampaignProEdit,
  type CampaignProEditValues,
  type HeavyEdits,
} from "./campaignApi";
import { useProEditEnabled } from "./api";
import {
  INTENSITIES,
  INTENSITY_LABEL,
  PRESET_LABEL,
  type Intensity,
  type PresetId,
} from "./options";

const HEAVY_OPTIONS: { value: HeavyEdits; label: string }[] = [
  { value: "unknown", label: "Not checked yet (counts as no)" },
  { value: "true", label: "Yes, the creator allows heavy edits" },
  { value: "false", label: "No, keep clips plain" },
];

const PRESET_OPTIONS = (Object.keys(PRESET_LABEL) as PresetId[]).map(
  (value) => ({ value, label: PRESET_LABEL[value] }),
);

const INTENSITY_OPTIONS = INTENSITIES.map((value) => ({
  value,
  label: INTENSITY_LABEL[value],
}));

function sameValues(a: CampaignProEditValues, b: CampaignProEditValues) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** The editable form once the autopilot settings are loaded. */
function ProEditForm({
  campaign,
  initial,
  settings,
}: {
  campaign: Campaign;
  initial: CampaignProEditValues;
  settings: NonNullable<ReturnType<typeof useAutopilotSettings>["data"]>;
}) {
  const [values, setValues] = useState(initial);
  const save = useSaveCampaignProEdit();
  const set = (change: Partial<CampaignProEditValues>) =>
    setValues((current) => ({ ...current, ...change }));
  const heavyAllowed = values.allowHeavyEdits === "true";

  return (
    <form
      aria-label={`Pro Edit settings of ${campaign.name}`}
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate({ campaign, settings, values });
      }}
      className="flex flex-col gap-4"
    >
      <SelectField
        label="Heavy edits allowed (allow_heavy_edits)"
        value={values.allowHeavyEdits}
        options={HEAVY_OPTIONS}
        onChange={(allowHeavyEdits) => set({ allowHeavyEdits })}
      />
      <ToggleRow
        label="Also make a Pro Edit variant"
        hint="The autopilot makes a Pro Edit of each draft next to the original; you approve either one or both."
        checked={values.enabled}
        onCheckedChange={(enabled) => set({ enabled })}
      />
      {values.enabled && !heavyAllowed && (
        <p
          role="status"
          className="flex items-start gap-2 text-caption text-muted-foreground"
        >
          <WarningIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
          No variant is made while heavy edits are not allowed. Set the campaign
          to "Yes" once the creator allows them.
        </p>
      )}
      <div className="grid grid-cols-2 gap-4">
        <SelectField
          label="Pro Edit preset"
          value={values.preset}
          options={PRESET_OPTIONS}
          onChange={(preset) => set({ preset })}
        />
        <SelectField<Intensity>
          label="Maximum intensity"
          value={values.maxIntensity}
          options={INTENSITY_OPTIONS}
          onChange={(maxIntensity) => set({ maxIntensity })}
        />
      </div>
      <div>
        <Button
          type="submit"
          disabled={save.isPending || sameValues(values, initial)}
        >
          <FloppyDiskIcon aria-hidden />
          {save.isPending ? "Saving…" : "Save Pro Edit settings"}
        </Button>
      </div>
    </form>
  );
}

/**
 * The Pro Edit settings of a campaign (SPEC-v3 1.5, 3.8): whether its
 * autopilot also makes a Pro Edit variant of each draft (default off), with
 * which preset and at most which intensity, and the campaign's
 * allow_heavy_edits flag that the autopilot needs to be "true". Nothing
 * while Pro Edit is off on the server.
 */
export function CampaignProEdit({ campaign }: { campaign: Campaign }) {
  const { enabled } = useProEditEnabled();
  const settings = useAutopilotSettings(campaign.id);
  if (!enabled) return null;
  const initial = settings.data && proEditValues(campaign, settings.data);
  return (
    <section
      aria-label="Pro Edit"
      className={cn(cardClass(), "flex flex-col gap-4 p-6")}
    >
      <h2 className="text-section">Pro Edit</h2>
      {settings.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the autopilot settings.
        </p>
      )}
      {settings.data && initial && (
        <ProEditForm
          key={JSON.stringify(initial)}
          campaign={campaign}
          initial={initial}
          settings={settings.data}
        />
      )}
    </section>
  );
}
