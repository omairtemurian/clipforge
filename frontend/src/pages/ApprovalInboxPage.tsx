import { CheckSquareIcon, TrayIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useCampaigns } from "@/api/campaigns";
import {
  useApproveCampaignDrafts,
  useApproveDraft,
  useDrafts,
  useRejectDraft,
  type RejectReason,
} from "@/api/drafts";
import type { Campaign, Draft } from "@/api/types";
import { DraftCard } from "@/components/DraftCard";
import { PageHeader } from "@/components/PageHeader";
import { PanelTabs } from "@/components/settings/PanelTabs";
import { Button, buttonVariants } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { useInboxShortcuts } from "@/hooks/useInboxShortcuts";
import { INBOX_PATH } from "@/components/navigation";
import { approvalMessage, stepIndex } from "@/lib/drafts";
import type { EditorBackState } from "@/lib/editorBack";
import { pageColumn } from "@/lib/surfaces";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

type InboxTab = "pending" | "needs_fix";

interface Rejecting {
  id: number;
  reason: RejectReason | null;
}

const EMPTY_TEXT: Record<InboxTab, { title: string; body: string }> = {
  pending: {
    title: "Nothing to approve",
    body: "When a campaign's autopilot finds a new upload, the clips that pass the campaign's rules wait here for you.",
  },
  needs_fix: {
    title: "Nothing needs a fix",
    body: "Clips of the autopilot that fail a campaign rule wait here, with the rules to fix.",
  },
};

const BACK_TO_INBOX: EditorBackState = {
  backTo: INBOX_PATH,
  backLabel: "Back to the approval inbox",
};

/** The campaign of each id. */
function byId(campaigns: Campaign[] | undefined): Map<number, Campaign> {
  return new Map((campaigns ?? []).map((campaign) => [campaign.id, campaign]));
}

/**
 * The Approval Inbox (SPEC-v2 3.19): the drafts that the campaigns'
 * autopilots made, to approve (scheduled into the next free slot), edit or
 * reject, with A/R/E and J/K on the selected one; the "Needs fix" tab holds
 * those that fail a rule. "Approve all" approves every waiting draft of the
 * chosen campaign after a confirm. Nothing is posted without the owner.
 */
export function ApprovalInboxPage() {
  const navigate = useNavigate();
  const [campaignId, setCampaignId] = useState<number | null>(null);
  const [tab, setTab] = useState<InboxTab>("pending");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [rejecting, setRejecting] = useState<Rejecting | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const campaigns = useCampaigns();
  const pending = useDrafts("pending", campaignId);
  const needsFix = useDrafts("needs_fix", campaignId);
  const approve = useApproveDraft();
  const reject = useRejectDraft();
  const approveAll = useApproveCampaignDrafts();

  const campaignOf = byId(campaigns.data);
  const current = tab === "pending" ? pending : needsFix;
  const drafts = current.data ?? [];
  const found = drafts.findIndex((draft) => draft.id === selectedId);
  const index = found === -1 ? 0 : found;
  const selected: Draft | undefined = drafts[index];
  const sending = (id: number) =>
    (approve.isPending && approve.variables === id) ||
    (reject.isPending && reject.variables.id === id);
  const chosenCampaign =
    campaignId === null ? undefined : campaignOf.get(campaignId);
  const pendingCount = pending.data?.length ?? 0;

  /** Select the draft after the decided one (or the one before). */
  const selectNeighbour = (draft: Draft) => {
    const at = drafts.findIndex((item) => item.id === draft.id);
    setSelectedId((drafts[at + 1] ?? drafts[at - 1])?.id ?? null);
  };
  const approveDraft = (draft: Draft) => {
    approve.mutate(draft.id, {
      onSuccess: (approval) => {
        toast.success(approvalMessage(approval));
        selectNeighbour(draft);
      },
    });
  };
  const rejectDraft = (draft: Draft, reason: RejectReason | null) => {
    reject.mutate(
      { id: draft.id, reason },
      {
        onSuccess: () => {
          toast.success("Rejected. The autopilot learns from it.");
          setRejecting(null);
          selectNeighbour(draft);
        },
      },
    );
  };
  const editDraft = (draft: Draft) =>
    void navigate(`/clips/${draft.clip_id}`, {
      state: BACK_TO_INBOX,
    });

  useInboxShortcuts(
    {
      approve: () => {
        if (selected && !rejecting && !sending(selected.id))
          approveDraft(selected);
      },
      reject: () => {
        if (!selected || sending(selected.id)) return;
        if (rejecting?.id === selected.id)
          rejectDraft(selected, rejecting.reason);
        else setRejecting({ id: selected.id, reason: null });
      },
      edit: () => selected && editDraft(selected),
      move: (step) => {
        setRejecting(null);
        setSelectedId(
          drafts[stepIndex(index, step, drafts.length)]?.id ?? null,
        );
      },
      cancel: () => setRejecting(null),
    },
    !confirmAll,
  );

  const list = (
    <div className="flex flex-col gap-4">
      {current.isPending &&
        [0, 1].map((key) => (
          <Skeleton key={key} className="h-72 rounded-2xl" />
        ))}
      {current.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the drafts.
        </p>
      )}
      {current.isSuccess && drafts.length === 0 && (
        <EmptyState
          icon={TrayIcon}
          title={EMPTY_TEXT[tab].title}
          action={
            <Link
              to="/campaigns"
              className={buttonVariants({ variant: "outline" })}
            >
              Open campaigns
            </Link>
          }
        >
          {EMPTY_TEXT[tab].body}
        </EmptyState>
      )}
      {drafts.map((draft) => (
        <DraftCard
          key={draft.id}
          draft={draft}
          campaign={campaignOf.get(draft.campaign_id)}
          selected={draft.id === selected?.id}
          rejecting={rejecting?.id === draft.id ? rejecting.reason : undefined}
          busy={sending(draft.id)}
          actions={{
            select: () => setSelectedId(draft.id),
            approve: () => approveDraft(draft),
            edit: () => editDraft(draft),
            startReject: () => setRejecting({ id: draft.id, reason: null }),
            pickReason: (reason) => setRejecting({ id: draft.id, reason }),
            reject: () => rejectDraft(draft, rejecting?.reason ?? null),
            cancelReject: () => setRejecting(null),
          }}
        />
      ))}
    </div>
  );

  return (
    <>
      <PageHeader
        title="Approval inbox"
        description="Clips your campaigns' autopilots made. Nothing is posted until you approve it. Keys: A approve, R reject, E edit, J/K next and previous."
        actions={
          <Button
            variant="outline"
            disabled={chosenCampaign === undefined || pendingCount === 0}
            title={chosenCampaign ? undefined : "Choose a campaign first"}
            onClick={() => setConfirmAll(true)}
          >
            <CheckSquareIcon aria-hidden />
            Approve all for this campaign
          </Button>
        }
      />
      <div className={cn(pageColumn(), "flex flex-col gap-4 pb-10")}>
        <label className="flex w-fit items-center gap-2 text-body font-medium">
          Campaign
          <NativeSelect
            value={campaignId ?? ""}
            onChange={(event) => {
              const value = event.target.value;
              setCampaignId(value === "" ? null : Number(value));
              setRejecting(null);
            }}
          >
            <option value="">All campaigns</option>
            {(campaigns.data ?? []).map((campaign) => (
              <option key={campaign.id} value={campaign.id}>
                {campaign.name}
              </option>
            ))}
          </NativeSelect>
        </label>
        <PanelTabs
          label="Drafts"
          value={tab}
          onChange={(next) => {
            setTab(next);
            setSelectedId(null);
            setRejecting(null);
          }}
          tabs={[
            {
              value: "pending",
              label: `To approve (${pendingCount})`,
              content: list,
            },
            {
              value: "needs_fix",
              label: `Needs fix (${needsFix.data?.length ?? 0})`,
              content: list,
            },
          ]}
        />
      </div>
      {confirmAll && chosenCampaign && (
        <ConfirmDialog
          title={`Approve ${pendingCount} ${pendingCount === 1 ? "clip" : "clips"}?`}
          confirmLabel="Approve all"
          onClose={() => setConfirmAll(false)}
          onConfirm={() =>
            approveAll.mutate(chosenCampaign.id, {
              onSuccess: (approvals) =>
                toast.success(
                  `Approved ${approvals.length} ${approvals.length === 1 ? "clip" : "clips"} of ${chosenCampaign.name}.`,
                ),
            })
          }
        >
          Every waiting clip of {chosenCampaign.name} is scheduled into the next
          free posting slot of its autopilot. Clips that need a fix are not
          included.
        </ConfirmDialog>
      )}
    </>
  );
}
