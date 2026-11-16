import { useState } from "react";
import { FloppyDiskIcon, TrashIcon } from "@phosphor-icons/react";
import { useDeleteCampaign, useSaveCampaign } from "@/api/campaigns";
import type { Campaign } from "@/api/types";
import { CampaignRulesFields } from "@/components/campaigns/CampaignRulesFields";
import { PermissionEvidence } from "@/components/campaigns/PermissionEvidence";
import { SelectField, TextField } from "@/components/campaigns/TextField";
import { Button } from "@/components/ui/button";
import {
  campaignBody,
  campaignChanges,
  draftOf,
  TEXT_MAX,
  validateCampaign,
  type CampaignDraft,
} from "@/lib/campaignForm";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

interface CampaignFormProps {
  /** The campaign to change; absent for a new one. */
  campaign?: Campaign;
  /** Changes whenever the saved screenshot may have changed. */
  version: number;
  onSaved: (saved: Campaign) => void;
  onDeleted: () => void;
}

/**
 * The create / edit form of a campaign. Everything is typed or pasted by the
 * owner (nothing is fetched from a campaign board). The parent keys it by
 * campaign id, so its draft starts fresh per campaign.
 */
export function CampaignForm({
  campaign,
  version,
  onSaved,
  onDeleted,
}: CampaignFormProps) {
  const [draft, setDraft] = useState<CampaignDraft>(() => draftOf(campaign));
  const [submitted, setSubmitted] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const save = useSaveCampaign(onSaved);
  const remove = useDeleteCampaign(onDeleted);

  const problems = validateCampaign(draft);
  const shown = submitted ? problems : {};
  const set = (change: Partial<CampaignDraft>) =>
    setDraft((current) => ({ ...current, ...change }));

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (Object.keys(problems).length > 0) return;
    save.mutate({
      id: campaign?.id ?? null,
      body: campaign ? campaignChanges(draft, campaign) : campaignBody(draft),
      screenshot: draft.screenshot,
    });
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label={campaign ? `Edit ${campaign.name}` : "New campaign"}
      className={cn(cardClass(), "flex flex-col gap-5 p-6")}
    >
      <h2 className="text-section">
        {campaign ? "Edit campaign" : "New campaign"}
      </h2>
      <div className="grid grid-cols-2 gap-4">
        <TextField
          label="Name"
          value={draft.name}
          maxLength={200}
          error={shown.name}
          onChange={(name) => set({ name })}
        />
        <TextField
          label="Creator"
          value={draft.creator}
          maxLength={200}
          onChange={(creator) => set({ creator })}
        />
        <SelectField
          label="Status"
          value={draft.status}
          options={[
            { value: "active", label: "Active" },
            { value: "paused", label: "Paused" },
            { value: "ended", label: "Ended" },
          ]}
          onChange={(status) => set({ status })}
        />
        <TextField
          label="End date"
          type="date"
          value={draft.endDate}
          onChange={(endDate) => set({ endDate })}
        />
        <SelectField
          label="Campaign board"
          value={draft.board}
          options={[
            { value: "whop", label: "Whop" },
            { value: "direct", label: "Direct deal" },
            { value: "other", label: "Other" },
          ]}
          onChange={(board) => set({ board })}
        />
        <SelectField
          label="Joining"
          value={draft.badge}
          options={[
            { value: "open", label: "Open" },
            { value: "register_first", label: "Register first" },
            { value: "apply_first", label: "Apply first" },
            { value: "paid", label: "Paid" },
          ]}
          onChange={(badge) => set({ badge })}
        />
        <TextField
          label="Campaign link"
          type="url"
          value={draft.campaignUrl}
          error={shown.campaignUrl}
          onChange={(campaignUrl) => set({ campaignUrl })}
        />
        <TextField
          label="Rate per 1,000 views (USD)"
          type="number"
          value={draft.rate}
          error={shown.rate}
          onChange={(rate) => set({ rate })}
        />
      </div>
      <TextField
        label="Creator channel links"
        rows={2}
        value={draft.channelUrls}
        error={shown.channelUrls}
        placeholder="One YouTube channel link per line"
        onChange={(channelUrls) => set({ channelUrls })}
      />
      <TextField
        label="Budget note"
        value={draft.budgetNote}
        maxLength={TEXT_MAX}
        onChange={(budgetNote) => set({ budgetNote })}
      />
      <CampaignRulesFields draft={draft} problems={shown} set={set} />
      <PermissionEvidence
        campaign={campaign}
        url={draft.permissionUrl}
        screenshot={draft.screenshot}
        urlError={shown.permissionUrl}
        screenshotError={shown.screenshot}
        version={version}
        onUrlChange={(permissionUrl) => set({ permissionUrl })}
        onScreenshotPick={(screenshot) => set({ screenshot })}
      />
      <TextField
        label="Notes"
        rows={2}
        value={draft.notes}
        maxLength={TEXT_MAX}
        onChange={(notes) => set({ notes })}
      />
      <div className="flex items-center gap-2">
        <Button type="submit" disabled={save.isPending}>
          <FloppyDiskIcon aria-hidden />
          {save.isPending
            ? "Saving…"
            : campaign
              ? "Save changes"
              : "Create campaign"}
        </Button>
        {campaign &&
          (confirmingDelete ? (
            <>
              <Button
                type="button"
                variant="destructive"
                disabled={remove.isPending}
                onClick={() => remove.mutate(campaign.id)}
              >
                Confirm delete
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setConfirmingDelete(false)}
              >
                Cancel
              </Button>
            </>
          ) : (
            <Button
              type="button"
              variant="ghost"
              onClick={() => setConfirmingDelete(true)}
            >
              <TrashIcon aria-hidden />
              Delete
            </Button>
          ))}
      </div>
    </form>
  );
}
