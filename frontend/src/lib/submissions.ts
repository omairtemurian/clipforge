import type { SubmissionPatch, SubmissionView } from "@/api/types";

export type SubmissionStatus = SubmissionView["status"];

export const STATUS_LABELS: Record<SubmissionStatus, string> = {
  not_submitted: "Not submitted",
  submitted: "Submitted",
  approved: "Approved",
  rejected: "Rejected",
  paid: "Paid",
};

/** The statuses a submission can move to from each one (as the server's
 * clipforge.submissions.TRANSITIONS). */
const MOVES: Record<SubmissionStatus, SubmissionStatus[]> = {
  not_submitted: ["submitted"],
  submitted: ["not_submitted", "approved", "rejected"],
  approved: ["submitted", "rejected", "paid"],
  rejected: ["submitted", "approved"],
  paid: ["approved"],
};

/** The board's answers the owner can record from `status`: the status
 * itself first, then the moves other than ticking or unticking
 * "submitted". */
export function answerOptions(status: SubmissionStatus): SubmissionStatus[] {
  const answers = MOVES[status].filter(
    (next) => next !== "submitted" && next !== "not_submitted",
  );
  return [status, ...answers];
}

/** The pill tone of a status. */
export function statusTone(
  status: SubmissionStatus,
): "neutral" | "primary" | "success" | "danger" {
  if (status === "not_submitted") return "neutral";
  if (status === "submitted") return "primary";
  return status === "rejected" ? "danger" : "success";
}

/** What the owner is typing for the numbers and notes of a submission. */
export interface DetailsDraft {
  status: SubmissionStatus;
  views: string;
  payout: string;
  notes: string;
}

/** The draft that shows the saved submission. */
export function detailsOf(submission: SubmissionView): DetailsDraft {
  return {
    status: submission.status,
    views: submission.approved_views?.toString() ?? "",
    payout: submission.payout_usd?.toString() ?? "",
    notes: submission.notes,
  };
}

/** A typed number: null for blank, NaN for anything else that is not a
 * non-negative number (whole when `whole`). */
function parsed(text: string, whole: boolean): number | null {
  if (text.trim() === "") return null;
  const value = Number(text);
  const ok = Number.isFinite(value) && value >= 0;
  return ok && (!whole || Number.isInteger(value)) ? value : NaN;
}

/** The problems with the typed numbers, by field. */
export function detailsProblems(draft: DetailsDraft): {
  views?: string;
  payout?: string;
} {
  return {
    views: Number.isNaN(parsed(draft.views, true))
      ? "Use a whole number, 0 or more."
      : undefined,
    payout: Number.isNaN(parsed(draft.payout, false))
      ? "Use a number, 0 or more."
      : undefined,
  };
}

/** The fields of `draft` that differ from the saved submission (an empty
 * patch: nothing to save); only call it when `detailsProblems` is empty. */
export function detailsPatch(
  submission: SubmissionView,
  draft: DetailsDraft,
): Partial<SubmissionPatch> {
  const patch: Partial<SubmissionPatch> = {};
  const views = parsed(draft.views, true);
  const payout = parsed(draft.payout, false);
  if (draft.status !== submission.status) patch.status = draft.status;
  if (views !== submission.approved_views) patch.approved_views = views;
  if (payout !== submission.payout_usd) patch.payout_usd = payout;
  if (draft.notes !== submission.notes) patch.notes = draft.notes;
  return patch;
}
