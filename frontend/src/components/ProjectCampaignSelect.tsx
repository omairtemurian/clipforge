import { useId } from "react";
import { Link } from "react-router-dom";
import { useCampaigns, useSetProjectCampaign } from "@/api/campaigns";
import type { Project } from "@/api/types";
import { NativeSelect } from "@/components/ui/native-select";

/**
 * Choose the campaign of a project: its preset (length range, caption
 * template, credit line, hashtags, mentions) is applied to the project and
 * its clips at once, and the clips are checked against its rules.
 */
export function ProjectCampaignSelect({ project }: { project: Project }) {
  const id = useId();
  const campaigns = useCampaigns();
  const apply = useSetProjectCampaign(project.id);
  const list = campaigns.data ?? [];

  if (
    campaigns.isSuccess &&
    list.length === 0 &&
    project.campaign_id === null
  ) {
    return (
      <p className="mt-3 text-caption text-muted-foreground">
        Clipping for a campaign?{" "}
        <Link to="/campaigns" className="text-primary-ink hover:underline">
          Add it under Campaigns
        </Link>{" "}
        to apply its rules to these clips.
      </p>
    );
  }

  return (
    <div className="mt-3 flex items-center gap-2 text-body text-muted-foreground">
      <label htmlFor={id}>Campaign</label>
      <NativeSelect
        id={id}
        value={project.campaign_id ?? ""}
        disabled={apply.isPending || !campaigns.isSuccess}
        onChange={(event) =>
          apply.mutate({
            campaign_id:
              event.target.value === "" ? null : Number(event.target.value),
          })
        }
        className="h-8 max-w-64"
      >
        <option value="">No campaign</option>
        {list.map((campaign) => (
          <option key={campaign.id} value={campaign.id}>
            {campaign.name}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
