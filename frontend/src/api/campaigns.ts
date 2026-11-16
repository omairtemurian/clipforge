import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import { apiFetch } from "./client";
import { projectsKey } from "./projects";
import type {
  Campaign,
  CampaignCheck,
  CampaignCreate,
  Project,
  ProjectCampaign,
} from "./types";

export const campaignsKey = ["campaigns"] as const;
export const campaignCheckKey = ["campaign-check"] as const;

/** Every campaign, oldest first. */
export function useCampaigns() {
  return useQuery({
    queryKey: campaignsKey,
    queryFn: () => apiFetch<Campaign[]>("/campaigns"),
  });
}

/** The pass/fail of each campaign rule for a clip (the rule checker). */
export function useCampaignCheck(clipId: number) {
  return useQuery({
    queryKey: [...campaignCheckKey, clipId],
    queryFn: () => apiFetch<CampaignCheck>(`/clips/${clipId}/campaign-check`),
  });
}

interface SaveCampaign {
  /** The campaign to change (PATCH the fields of `body`, none: nothing is
   * sent); null creates one (POST) from the full `body`. */
  id: number | null;
  body: Partial<CampaignCreate>;
  /** The permission screenshot picked now, uploaded after the save. */
  screenshot: File | null;
}

/** Create or change a campaign, then upload its permission screenshot if one
 * was picked; the saved campaign is passed to `onSaved`. */
export function useSaveCampaign(onSaved: (saved: Campaign) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body, screenshot }: SaveCampaign) => {
      const changed = id === null || Object.keys(body).length > 0;
      const saved = await apiFetch<Campaign>(
        id === null ? "/campaigns" : `/campaigns/${id}`,
        changed
          ? { method: id === null ? "POST" : "PATCH", json: body }
          : { method: "GET" },
      );
      if (!screenshot) return saved;
      const form = new FormData();
      form.set("file", screenshot);
      return apiFetch<Campaign>(
        `/campaigns/${saved.id}/permission-screenshot`,
        {
          method: "POST",
          body: form,
        },
      );
    },
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: campaignsKey });
      await queryClient.invalidateQueries({ queryKey: campaignCheckKey });
      toast.success(`Saved "${saved.name}".`);
      onSaved(saved);
    },
  });
}

/** Delete a campaign; its projects stay, without a campaign. */
export function useDeleteCampaign(onDeleted: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/campaigns/${id}`, { method: "DELETE" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: campaignsKey });
      await queryClient.invalidateQueries({ queryKey: projectsKey });
      await queryClient.invalidateQueries({ queryKey: campaignCheckKey });
      toast.success("Campaign deleted.");
      onDeleted();
    },
  });
}

/** Make a campaign the project's (null: leave it) and apply its preset to
 * the project and its clips. */
export function useSetProjectCampaign(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCampaign) =>
      apiFetch<Project>(`/projects/${projectId}/campaign`, {
        method: "PUT",
        json: body,
      }),
    onSuccess: async (_project, body) => {
      await queryClient.invalidateQueries({ queryKey: projectsKey });
      await queryClient.invalidateQueries({ queryKey: ["clips"] });
      await queryClient.invalidateQueries({ queryKey: campaignCheckKey });
      toast.success(
        body.campaign_id === null
          ? "The project left its campaign."
          : "Campaign applied to the project and its clips.",
      );
    },
  });
}
