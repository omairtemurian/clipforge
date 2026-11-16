import {
  PlusIcon,
  ShieldCheckIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import type { Campaign } from "@/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { choiceClass } from "@/lib/surfaces";

interface CampaignListProps {
  campaigns: Campaign[];
  /** The id of the campaign being edited; null while a new one is made. */
  selectedId: number | null;
  onSelect: (id: number) => void;
  onNew: () => void;
}

/** The campaigns as a column of cards (name, creator, status, permission) and a New button. */
export function CampaignList({
  campaigns,
  selectedId,
  onSelect,
  onNew,
}: CampaignListProps) {
  return (
    <div className="flex flex-col gap-3">
      <Button
        onClick={onNew}
        variant={selectedId === null ? "secondary" : "default"}
      >
        <PlusIcon aria-hidden />
        New campaign
      </Button>
      <ul aria-label="Campaigns" className="flex flex-col gap-2">
        {campaigns.map((campaign) => (
          <li key={campaign.id}>
            <button
              type="button"
              onClick={() => onSelect(campaign.id)}
              aria-current={campaign.id === selectedId}
              className={cn(
                choiceClass(campaign.id === selectedId),
                "flex w-full cursor-pointer items-center gap-3",
              )}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-body font-medium">
                  {campaign.name}
                </span>
                <span className="block truncate text-caption text-muted-foreground">
                  {campaign.creator_name || "No creator"} · {campaign.status}
                </span>
              </span>
              {campaign.permission_complete ? (
                <ShieldCheckIcon
                  className="size-4 shrink-0 text-success"
                  aria-label="Permission complete"
                />
              ) : (
                <WarningCircleIcon
                  className="size-4 shrink-0 text-warning"
                  aria-label="Permission missing"
                />
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
