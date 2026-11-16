import { PaperPlaneTiltIcon } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { useReadySubmissions } from "@/api/submissions";
import { PageHeader } from "@/components/PageHeader";
import { SubmissionItem } from "@/components/submissions/SubmissionItem";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/**
 * The "Ready to submit" list (SPEC-v2 3.19): the posts of all campaigns that
 * are published but not submitted on their campaign board yet. The owner
 * copies a post's URL with the campaign's required information, submits it on
 * the board by hand (ClipForge never automates a board) and ticks it here;
 * a ticked post leaves the list and its numbers go on in the campaign.
 */
export function ReadyToSubmitPage() {
  const ready = useReadySubmissions();
  const list = ready.data ?? [];

  return (
    <>
      <PageHeader
        title="Ready to submit"
        description={
          list.length > 0
            ? `${list.length} published ${list.length === 1 ? "post is" : "posts are"} waiting for you to submit on the campaign board. Copy it, submit it there yourself, then tick it here.`
            : "Published posts of your campaigns that you have not submitted on the campaign board yet."
        }
      />
      <div className={cn(pageColumn(), "flex flex-col gap-4 pb-10")}>
        {ready.isPending && (
          <Skeleton className="h-40 rounded-2xl" aria-label="Loading" />
        )}
        {ready.isError && (
          <p role="alert" className="text-body text-destructive">
            Could not load the posts to submit.
          </p>
        )}
        {ready.isSuccess && list.length === 0 && (
          <EmptyState
            icon={PaperPlaneTiltIcon}
            title="Nothing to submit"
            action={
              <Link
                to="/campaigns"
                className={buttonVariants({ variant: "outline" })}
              >
                Open campaigns
              </Link>
            }
          >
            Posts of your campaigns' clips appear here once they are published.
          </EmptyState>
        )}
        <ul aria-label="Posts to submit" className="flex flex-col gap-3">
          {list.map((submission) => (
            <SubmissionItem
              key={submission.id}
              submission={submission}
              showCampaign
            />
          ))}
        </ul>
      </div>
    </>
  );
}
