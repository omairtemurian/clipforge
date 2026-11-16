import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { campaignsKey } from "@/api/campaigns";
import type {
  AutopilotSettings,
  AutopilotSettingsUpdate,
  Campaign,
} from "@/api/types";
import { toast } from "@/lib/toast";

export type HeavyEdits = Campaign["allow_heavy_edits"];

/** What the campaign's Pro Edit section edits (SPEC-v3 3.8). */
export interface CampaignProEditValues {
  allowHeavyEdits: HeavyEdits;
  enabled: AutopilotSettings["proedit_enabled"];
  preset: AutopilotSettings["proedit_preset"];
  maxIntensity: AutopilotSettings["proedit_max_intensity"];
}

const autopilotKey = (campaignId: number) =>
  ["campaigns", campaignId, "autopilot"] as const;

/** The autopilot settings of campaign campaignId
 * (GET /campaigns/{id}/autopilot). */
export function useAutopilotSettings(campaignId: number) {
  return useQuery({
    queryKey: autopilotKey(campaignId),
    queryFn: () =>
      apiFetch<AutopilotSettings>(`/campaigns/${campaignId}/autopilot`),
  });
}

/** The values the section starts with. */
export function proEditValues(
  campaign: Campaign,
  settings: AutopilotSettings,
): CampaignProEditValues {
  return {
    allowHeavyEdits: campaign.allow_heavy_edits,
    enabled: settings.proedit_enabled,
    preset: settings.proedit_preset,
    maxIntensity: settings.proedit_max_intensity,
  };
}

/** The body of PUT /campaigns/{id}/autopilot: the saved settings (a PUT
 * replaces them all) with the Pro Edit values. */
export function autopilotBody(
  settings: AutopilotSettings,
  values: CampaignProEditValues,
): AutopilotSettingsUpdate {
  const saved: Partial<AutopilotSettings> = { ...settings };
  delete saved.campaign_id;
  return {
    ...(saved as AutopilotSettingsUpdate),
    proedit_enabled: values.enabled,
    proedit_preset: values.preset,
    proedit_max_intensity: values.maxIntensity,
  };
}

interface SaveProEdit {
  campaign: Campaign;
  settings: AutopilotSettings;
  values: CampaignProEditValues;
}

/** Save the campaign's Pro Edit values: allow_heavy_edits on the campaign
 * (only if it changed) and the switch, preset and maximum intensity in its
 * autopilot settings. */
export function useSaveCampaignProEdit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ campaign, settings, values }: SaveProEdit) => {
      if (values.allowHeavyEdits !== campaign.allow_heavy_edits) {
        await apiFetch<Campaign>(`/campaigns/${campaign.id}`, {
          method: "PATCH",
          json: { allow_heavy_edits: values.allowHeavyEdits },
        });
      }
      return apiFetch<AutopilotSettings>(
        `/campaigns/${campaign.id}/autopilot`,
        { method: "PUT", json: autopilotBody(settings, values) },
      );
    },
    onSuccess: async (_saved, { campaign }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: campaignsKey }),
        queryClient.invalidateQueries({
          queryKey: autopilotKey(campaign.id),
        }),
        queryClient.invalidateQueries({ queryKey: ["proedit", "choices"] }),
      ]);
      toast.success("Saved the Pro Edit settings.");
    },
  });
}
