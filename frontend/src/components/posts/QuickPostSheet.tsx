import { Dialog } from "radix-ui";
import {
  CircleNotchIcon,
  PaperPlaneTiltIcon,
  XIcon,
} from "@phosphor-icons/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAccounts } from "@/api/accounts";
import { apiUrl } from "@/api/client";
import { useQuickPost, type QuickTargets } from "@/api/quickPost";
import type { Clip } from "@/api/types";
import { Button } from "@/components/ui/button";
import { canPost, platformsOf, postProblem, postText } from "@/lib/postForm";
import {
  defaultAccounts,
  lastPlatforms,
  rememberPlatforms,
  startingIds,
} from "@/lib/quickPost";
import { toast } from "@/lib/toast";
import { PostAccounts } from "./PostAccounts";
import { PostTexts } from "./PostTexts";
import { usePostDrafts } from "./usePostDrafts";
import { useQuickRender } from "./useQuickRender";

interface QuickPostSheetProps {
  clip: Clip;
  /** Pick the accounts by hand instead of using each platform's default. */
  choose: boolean;
  onClose: () => void;
}

/**
 * The confirm sheet of the one-click "Post" button: the clip is rendered if
 * needed, the AI writes the text of each platform, and one "Post now" sends
 * it to each platform's default account (or to the accounts picked in
 * "Choose accounts…").
 */
export function QuickPostSheet({ clip, choose, onClose }: QuickPostSheetProps) {
  const accounts = useAccounts();
  const send = useQuickPost(clip.id);
  const render = useQuickRender(clip);
  const [touched, setTouched] = useState<ReadonlySet<number> | null>(null);

  const postable = (accounts.data ?? []).filter(canPost);
  const offered = choose ? postable : defaultAccounts(postable);
  const chosen = touched ?? startingIds(postable, lastPlatforms());
  const picked = offered.filter((account) => chosen.has(account.id));
  const platforms = platformsOf(picked);
  const { drafts, change, rewrite, rewriting, failed, writing } = usePostDrafts(
    clip,
    platforms,
    picked,
  );
  const problem = postProblem(picked, drafts);
  const blocked =
    problem !== null ||
    render.state !== "ready" ||
    writing.length > 0 ||
    send.isPending;

  function toggle(id: number) {
    const next = new Set(chosen);
    if (!next.delete(id)) next.add(id);
    setTouched(next);
  }

  function submit() {
    const targets: QuickTargets = choose
      ? { kind: "accounts", accountIds: picked.map((account) => account.id) }
      : { kind: "defaults", platforms };
    const texts = Object.fromEntries(
      platforms.map((platform) => [
        platform,
        postText(platform, drafts[platform]),
      ]),
    );
    send.mutate(
      { targets, texts },
      {
        onSuccess: (posts) => {
          rememberPlatforms(platforms);
          const count = posts.length === 1 ? "1 post" : `${posts.length} posts`;
          toast.success(`Publishing ${count} now.`);
          onClose();
        },
      },
    );
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-[calc(100%-2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col gap-5 overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-popover">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <Dialog.Title className="text-lg font-semibold">
                Post clip
              </Dialog.Title>
              <Dialog.Description className="mt-1 truncate text-sm text-muted-foreground">
                {clip.title}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Close">
                <XIcon aria-hidden />
              </Button>
            </Dialog.Close>
          </div>
          {accounts.isSuccess && offered.length === 0 ? (
            <p role="status" className="text-sm text-muted-foreground">
              No account to post to yet.{" "}
              <Link to="/accounts" className="underline" onClick={onClose}>
                Sign in on the Social accounts page
              </Link>{" "}
              and star the account each platform should use.
            </p>
          ) : (
            <div className="grid gap-6 md:grid-cols-[14rem_1fr]">
              <PostAccounts
                accounts={offered}
                loading={accounts.isPending}
                chosen={chosen}
                onToggle={toggle}
              />
              <PostTexts
                platforms={platforms}
                drafts={drafts}
                onChange={change}
                thumbnailUrl={apiUrl(`/media/${clip.project_id}/thumbnail`)}
                writing={writing}
                failed={failed}
                rewriting={rewriting}
                onRewrite={rewrite}
              />
            </div>
          )}
          <RenderLine state={render.state} onRetry={render.retry} />
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
            {problem && offered.length > 0 && (
              <p role="status" className="text-sm text-muted-foreground">
                {problem}
              </p>
            )}
            <Button
              type="button"
              className="ml-auto"
              disabled={blocked}
              onClick={submit}
            >
              {send.isPending ? (
                <CircleNotchIcon className="animate-spin" aria-hidden />
              ) : (
                <PaperPlaneTiltIcon aria-hidden />
              )}
              Post now
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** What the clip's video is doing: nothing to say once it is rendered. */
function RenderLine({
  state,
  onRetry,
}: {
  state: "ready" | "rendering" | "failed";
  onRetry: () => void;
}) {
  if (state === "ready") return null;
  if (state === "failed") {
    return (
      <p
        role="alert"
        className="flex items-center gap-2 text-sm text-destructive"
      >
        The clip could not be rendered.
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </p>
    );
  }
  return (
    <p
      role="status"
      className="flex items-center gap-2 text-xs text-muted-foreground"
    >
      <CircleNotchIcon className="size-3 animate-spin" aria-hidden />
      Rendering the clip…
    </p>
  );
}
