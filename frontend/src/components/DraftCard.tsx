import {
  CheckIcon,
  NotePencilIcon,
  ScissorsIcon,
  XIcon,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { useClip } from "@/api/clips";
import type { RejectReason } from "@/api/drafts";
import type { Campaign, Clip, Draft } from "@/api/types";
import { DraftRules } from "@/components/drafts/DraftRules";
import { DraftSource } from "@/components/drafts/DraftSource";
import { RejectReasons } from "@/components/drafts/RejectReasons";
import { ScoreBadge } from "@/components/ScoreBadge";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import {
  InboxVariants,
  ProEditBadge,
  ProEditButton,
  VariantOf,
} from "@/features/proedit";
import { rateLabel } from "@/lib/drafts";
import { previewUrl } from "@/lib/previewUrl";
import { cardClass, MEDIA_FRAME } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** What the owner can do with a draft of the inbox. */
export interface DraftActions {
  select: () => void;
  approve: () => void;
  edit: () => void;
  startReject: () => void;
  pickReason: (reason: RejectReason | null) => void;
  reject: () => void;
  cancelReject: () => void;
}

interface DraftCardProps {
  draft: Draft;
  campaign: Campaign | undefined;
  selected: boolean;
  /** The picked reason while the reject reasons are open (null: none
   * picked); undefined while they are closed. */
  rejecting: RejectReason | null | undefined;
  /** A decision about this draft is being sent. */
  busy: boolean;
  actions: DraftActions;
}

/** The clip's preview: it plays muted and looping right away. */
function DraftPreview({ clip }: { clip: Clip }) {
  const [broken, setBroken] = useState(false);
  return (
    <div className={cn(MEDIA_FRAME, "aspect-[9/16] w-36 shrink-0 sm:w-44")}>
      {!broken && (
        <video
          src={previewUrl(clip)}
          aria-label={`Preview of ${clip.title}`}
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          onError={() => setBroken(true)}
          className="absolute inset-0 size-full object-cover"
        />
      )}
    </div>
  );
}

/** A small key hint on an action button ("A"). */
function Key({ children }: { children: string }) {
  return (
    <kbd
      aria-hidden
      className="rounded bg-foreground/10 px-1 text-micro font-medium"
    >
      {children}
    </kbd>
  );
}

/** The review notes of the owner and of agents, oldest first. */
function DraftNotes({ draft }: { draft: Draft }) {
  if (draft.notes.length === 0) return null;
  return (
    <ul aria-label="Review notes" className="flex flex-col gap-1">
      {draft.notes.map((note) => (
        <li
          key={note.at}
          className="flex gap-1.5 text-caption text-muted-foreground"
        >
          <NotePencilIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>
            <span className="font-medium text-foreground">
              {note.by === "agent" ? "Agent" : "You"}:
            </span>{" "}
            {note.text}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * A draft of the Approval Inbox: the clip's autoplaying preview, its title,
 * description and hashtags, the campaign and its rate, the virality score,
 * the rule check, the source video and its freshness, the review notes, and
 * Approve (A), Edit (E), Pro Edit and Reject (R, with optional reason
 * chips); an original shows its Pro Edit variants to approve as well.
 */
export function DraftCard({
  draft,
  campaign,
  selected,
  rejecting,
  busy,
  actions,
}: DraftCardProps) {
  const clip = useClip(draft.clip_id);
  const ref = useRef<HTMLElement>(null);
  const title = clip.data?.title ?? `Clip ${draft.clip_id}`;

  useEffect(() => {
    if (selected) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);

  return (
    <article
      ref={ref}
      aria-label={`Draft: ${title}`}
      aria-current={selected ? "true" : undefined}
      onClick={actions.select}
      className={cn(
        cardClass(!selected),
        "flex gap-5 p-4",
        selected && "border-primary ring-3 ring-primary/20",
      )}
    >
      {clip.data ? (
        <DraftPreview clip={clip.data} />
      ) : (
        <Skeleton className="aspect-[9/16] w-36 shrink-0 rounded-xl sm:w-44" />
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Pill tone="primary">{campaign?.name ?? "Campaign"}</Pill>
            {campaign && <Pill>{rateLabel(campaign)}</Pill>}
            {clip.data?.variant === "pro_edit" && <ProEditBadge />}
            {draft.status === "needs_fix" && (
              <Pill tone="danger">Needs fix</Pill>
            )}
          </div>
          {clip.data && <ScoreBadge clip={clip.data} />}
        </div>
        {clip.isError ? (
          <p role="alert" className="text-body text-destructive">
            Could not load the clip.
          </p>
        ) : (
          <div className="flex flex-col gap-1">
            <h2 className="text-section">{title}</h2>
            {clip.data && <VariantOf clip={clip.data} />}
            {clip.data?.description && (
              <p className="line-clamp-3 text-body text-muted-foreground">
                {clip.data.description}
              </p>
            )}
            {clip.data && clip.data.hashtags.length > 0 && (
              <p className="text-caption text-primary-ink">
                {clip.data.hashtags.map((tag) => `#${tag}`).join(" ")}
              </p>
            )}
          </div>
        )}
        {clip.data && <DraftSource projectId={clip.data.project_id} />}
        <DraftRules results={draft.rule_results} />
        <DraftNotes draft={draft} />
        {clip.data && (
          <InboxVariants
            clip={clip.data}
            draft={draft}
            onApproveOriginal={actions.approve}
            busy={busy}
          />
        )}
        {rejecting === undefined ? (
          <div className="mt-auto flex flex-wrap gap-2 pt-1">
            <Button
              aria-label="Approve"
              aria-keyshortcuts="A"
              disabled={busy}
              onClick={actions.approve}
            >
              <CheckIcon aria-hidden />
              Approve <Key>A</Key>
            </Button>
            <Button
              variant="outline"
              aria-label="Edit"
              aria-keyshortcuts="E"
              onClick={actions.edit}
            >
              <ScissorsIcon aria-hidden />
              Edit <Key>E</Key>
            </Button>
            {clip.data && <ProEditButton clip={clip.data} />}
            <Button
              variant="ghost"
              aria-label="Reject"
              aria-keyshortcuts="R"
              disabled={busy}
              onClick={actions.startReject}
            >
              <XIcon aria-hidden />
              Reject <Key>R</Key>
            </Button>
          </div>
        ) : (
          <RejectReasons
            title={title}
            reason={rejecting}
            onPick={actions.pickReason}
            onReject={actions.reject}
            onCancel={actions.cancelReject}
            busy={busy}
          />
        )}
      </div>
    </article>
  );
}
