import { useState } from "react";
import { useCampaigns } from "@/api/campaigns";
import { CampaignForm } from "@/components/CampaignForm";
import { CampaignList } from "@/components/campaigns/CampaignList";
import { CampaignProEdit } from "@/features/proedit";
import { PageHeader } from "@/components/PageHeader";
import { SubmissionTracker } from "@/components/SubmissionTracker";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** Campaigns: the saved ones on the left, the form of the chosen one (or of
 * a new one) on the right. */
export function CampaignsPage() {
  const campaigns = useCampaigns();
  // undefined: the first campaign (or a new one when there is none).
  const [chosen, setChosen] = useState<number | "new" | undefined>();
  const list = campaigns.data ?? [];
  const selected =
    chosen === "new"
      ? undefined
      : (list.find((c) => c.id === chosen) ?? list[0]);
  const creating = campaigns.isSuccess && selected === undefined;

  return (
    <>
      <PageHeader
        title="Campaigns"
        description="The clipping campaigns you work on: type or paste their rules and keep the proof that you may clip the creator. Clips are checked against the rules before they are published."
      />
      <div
        className={cn(
          pageColumn(),
          "grid gap-6 pb-10 md:grid-cols-[16rem_1fr]",
        )}
      >
        <CampaignList
          campaigns={list}
          selectedId={selected?.id ?? null}
          onSelect={setChosen}
          onNew={() => setChosen("new")}
        />
        {campaigns.isError && (
          <p role="alert" className="text-body text-destructive">
            Could not load the campaigns.
          </p>
        )}
        {(creating || selected) && (
          <div className="flex min-w-0 flex-col gap-8">
            <CampaignForm
              key={selected?.id ?? "new"}
              campaign={selected}
              version={campaigns.dataUpdatedAt}
              onSaved={(saved) => setChosen(saved.id)}
              onDeleted={() => setChosen(undefined)}
            />
            {selected && (
              <CampaignProEdit
                key={`proedit-${selected.id}`}
                campaign={selected}
              />
            )}
            {selected && (
              <SubmissionTracker
                campaignId={selected.id}
                rate={selected.rate_per_1k_usd}
              />
            )}
          </div>
        )}
      </div>
    </>
  );
}
