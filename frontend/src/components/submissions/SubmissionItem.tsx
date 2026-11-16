import { ArrowSquareOutIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { useUpdateSubmission } from "@/api/submissions";
import type { SubmissionView } from "@/api/types";
import { CopyButton } from "@/components/agents/CopyButton";
import { TextField } from "@/components/campaigns/TextField";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Pill } from "@/components/ui/pill";
import { platformLabel } from "@/lib/platforms";
import {
  STATUS_LABELS,
  answerOptions,
  detailsOf,
  detailsPatch,
  detailsProblems,
  statusTone,
  type DetailsDraft,
} from "@/lib/submissions";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/** The board's answer, the approved views, the payout and the notes of a
 * submission, with a Save that sends what changed. It starts over from the
 * saved submission (the parent re-keys it) after each save. */
function SubmissionDetails({ submission }: { submission: SubmissionView }) {
  const update = useUpdateSubmission();
  const [draft, setDraft] = useState<DetailsDraft>(detailsOf(submission));
  const problems = detailsProblems(draft);
  const patch = detailsPatch(submission, draft);
  const invalid = problems.views !== undefined || problems.payout !== undefined;
  const dirty = Object.keys(patch).length > 0;
  const change = (changes: Partial<DetailsDraft>) =>
    setDraft({ ...draft, ...changes });

  return (
    <form
      aria-label={`Details of ${submission.clip_title}`}
      className="grid gap-3 sm:grid-cols-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (dirty && !invalid) {
          update.mutate({ id: submission.id, patch });
        }
      }}
    >
      <label className="flex flex-col gap-2 text-body font-medium">
        Answer of the board
        <NativeSelect
          block
          value={draft.status}
          onChange={(event) =>
            change({ status: event.target.value as DetailsDraft["status"] })
          }
        >
          {answerOptions(submission.status).map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </NativeSelect>
      </label>
      <TextField
        label="Approved views"
        type="number"
        value={draft.views}
        error={problems.views}
        onChange={(views) => change({ views })}
      />
      <TextField
        label="Payout (USD)"
        type="number"
        value={draft.payout}
        error={problems.payout}
        onChange={(payout) => change({ payout })}
      />
      <div className="sm:col-span-3">
        <TextField
          label="Notes"
          value={draft.notes}
          maxLength={2000}
          onChange={(notes) => change({ notes })}
        />
      </div>
      <div className="sm:col-span-3">
        <Button
          type="submit"
          size="sm"
          disabled={!dirty || invalid || update.isPending}
        >
          Save details
        </Button>
      </div>
    </form>
  );
}

/** One published post of a campaign: its link, "Copy for submission" (the
 * URL with the campaign's required information), the tick that it was
 * submitted on the campaign board and, once it was, the board's answer
 * and the numbers. showCampaign adds the campaign's name (lists of several
 * campaigns). */
export function SubmissionItem({
  submission,
  showCampaign = false,
}: {
  submission: SubmissionView;
  showCampaign?: boolean;
}) {
  const update = useUpdateSubmission();
  const { status } = submission;
  const ticked = status !== "not_submitted";
  // Approved, rejected and paid posts leave "submitted" through the answer.
  const tickable = status === "not_submitted" || status === "submitted";

  return (
    <li className={cn(cardClass(), "flex flex-col gap-3 p-4")}>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="neutral">{platformLabel(submission.platform)}</Pill>
        {showCampaign && submission.campaign_name && (
          <Pill tone="primary">{submission.campaign_name}</Pill>
        )}
        <span className="min-w-0 flex-1 truncate text-body font-medium">
          {submission.clip_title || `Clip ${submission.clip_id}`}
        </span>
        <Pill tone={statusTone(status)}>{STATUS_LABELS[status]}</Pill>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <a
          href={submission.post_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-w-0 items-center gap-1 text-body text-primary-ink underline-offset-2 hover:underline"
        >
          <span className="truncate">{submission.post_url}</span>
          <ArrowSquareOutIcon aria-hidden className="size-4 shrink-0" />
        </a>
        <CopyButton
          text={submission.copy_text}
          caption="Copy for submission"
          label={`Copy for submission: ${submission.clip_title}`}
        />
      </div>
      <label
        className={cn(
          "flex items-center gap-2 text-body",
          !tickable && "text-muted-foreground",
        )}
      >
        <input
          type="checkbox"
          className="size-4 accent-primary"
          checked={ticked}
          disabled={!tickable || update.isPending}
          onChange={(event) =>
            update.mutate({
              id: submission.id,
              patch: {
                status: event.target.checked ? "submitted" : "not_submitted",
              },
            })
          }
        />
        Submitted on the campaign board
        {submission.submitted_at && (
          <span className="text-caption text-muted-foreground">
            {new Date(submission.submitted_at).toLocaleDateString()}
          </span>
        )}
      </label>
      {ticked && (
        <SubmissionDetails
          key={JSON.stringify(detailsOf(submission))}
          submission={submission}
        />
      )}
    </li>
  );
}
