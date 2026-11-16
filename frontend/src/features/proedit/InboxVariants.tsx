import { CheckIcon, ChecksIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Clip, Draft } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { approvalMessage } from "@/lib/drafts";
import { editsVersion } from "@/lib/previewUrl";
import { MEDIA_FRAME } from "@/lib/surfaces";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { useProEditEnabled, useProEditVariants } from "./api";
import { useApproveVariant } from "./draftApi";
import { proEditPath, variantVideoUrl } from "./paths";
import { ProEditBadge } from "./VariantBadge";

interface InboxVariantsProps {
  /** The original clip of the inbox draft. */
  clip: Clip;
  draft: Draft;
  /** Approve the original's draft (the card's Approve). */
  onApproveOriginal: () => void;
  /** A decision about the original is being sent. */
  busy: boolean;
}

/** A Pro Edit variant under its original's inbox draft: its rendered Pro
 * Edit video (not the v1 preview of /clips/{id}/preview, which renders the
 * clip without its Pro Edit plan), the badge, title and status, and Approve
 * Pro Edit / Approve both. */
function VariantCard({
  variant,
  draft,
  onApproveOriginal,
  busy,
}: Omit<InboxVariantsProps, "clip"> & { variant: Clip }) {
  const approve = useApproveVariant();
  const [broken, setBroken] = useState(false);
  const ready = variant.status === "rendered";
  const waiting = draft.status === "pending" || draft.status === "needs_fix";

  const approveVariant = (andOriginal: boolean) =>
    approve.mutate(
      { variantId: variant.id, campaignId: draft.campaign_id },
      {
        onSuccess: (approval) => {
          toast.success(`Pro Edit — ${approvalMessage(approval)}`);
          if (andOriginal) onApproveOriginal();
        },
      },
    );

  return (
    <li
      aria-label={`Pro Edit variant: ${variant.title}`}
      className="flex gap-3 rounded-xl border border-border bg-field p-2.5"
    >
      <div className={cn(MEDIA_FRAME, "aspect-[9/16] w-14 shrink-0")}>
        {ready && !broken && (
          <video
            src={variantVideoUrl(variant.id, editsVersion(variant))}
            aria-label={`Preview of ${variant.title}`}
            muted
            loop
            autoPlay
            playsInline
            preload="metadata"
            onError={() => setBroken(true)}
            className="absolute inset-0 size-full object-cover"
          />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <ProEditBadge />
          <Pill tone={ready ? "success" : "neutral"}>{variant.status}</Pill>
        </div>
        <Link
          to={proEditPath(variant.parent_clip_id ?? variant.id, variant.id)}
          title="Open the Pro Edit variants"
          className="truncate text-body font-medium underline-offset-4 hover:underline"
        >
          {variant.title}
        </Link>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!ready || approve.isPending}
            title={ready ? undefined : "Wait for the Pro Edit render"}
            onClick={(event) => {
              event.stopPropagation();
              approveVariant(false);
            }}
          >
            <CheckIcon aria-hidden />
            Approve Pro Edit
          </Button>
          {waiting && (
            <Button
              size="sm"
              disabled={!ready || approve.isPending || busy}
              title={ready ? undefined : "Wait for the Pro Edit render"}
              onClick={(event) => {
                event.stopPropagation();
                approveVariant(true);
              }}
            >
              <ChecksIcon aria-hidden />
              Approve both
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}

/**
 * The Pro Edit variants of an inbox draft's original clip as linked cards
 * (SPEC-v3 3.8): the owner approves the original (the card's Approve), a
 * Pro Edit, or both. Nothing while Pro Edit is off or the clip has none.
 */
export function InboxVariants(props: InboxVariantsProps) {
  const { enabled } = useProEditEnabled();
  const original = props.clip.variant === "original";
  if (!enabled || !original) return null;
  return <VariantList {...props} />;
}

function VariantList({ clip, ...rest }: InboxVariantsProps) {
  const variants = useProEditVariants(clip.id);
  if (!variants.data || variants.data.length === 0) return null;
  return (
    <ul aria-label="Pro Edit variants" className="flex flex-col gap-2">
      {variants.data.map((variant) => (
        <VariantCard key={variant.id} variant={variant} {...rest} />
      ))}
    </ul>
  );
}
