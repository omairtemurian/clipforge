import { Dialog } from "radix-ui";
import { XIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { useAccounts } from "@/api/accounts";
import { apiUrl } from "@/api/client";
import { coverUrl } from "@/api/thumbnails";
import { useSchedulePosts, type PostWhen as When } from "@/api/posts";
import type { Asset, Clip, Post } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  DEFAULT_BULK,
  bulkBody,
  canPost,
  futureTime,
  platformsOf,
  postProblem,
  scheduledLine,
  targetsOf,
  whenProblem,
  type WhenMode,
} from "@/lib/postForm";
import { toast } from "@/lib/toast";
import { PostAccounts } from "./PostAccounts";
import { PostCover } from "./PostCover";
import { PostTexts } from "./PostTexts";
import { PostWhen } from "./PostWhen";
import { usePostDrafts } from "./usePostDrafts";

interface SchedulePostModalProps {
  clip: Clip;
  onClose: () => void;
}

/** The toast after the posts were sent. */
function sentLine(mode: WhenMode, posts: Post[]): string {
  if (mode !== "now") return scheduledLine(posts);
  const count = posts.length === 1 ? "1 post" : `${posts.length} posts`;
  return `Publishing ${count} now.`;
}

/**
 * The "Schedule post" modal of a clip (SPEC-v2 3.10): the accounts to post
 * to (left), what the post says on each platform (right) and when it goes
 * out (footer: now, at a picked time or in each account's next free slots
 * of the bulk rules).
 */
export function SchedulePostModal({ clip, onClose }: SchedulePostModalProps) {
  const accounts = useAccounts();
  const send = useSchedulePosts(clip.id);
  const [chosen, setChosen] = useState<ReadonlySet<number>>(new Set());
  const [cover, setCover] = useState<Asset | null>(null);
  const [mode, setMode] = useState<WhenMode>("now");
  const [at, setAt] = useState("");
  const [bulk, setBulk] = useState(DEFAULT_BULK);

  const postable = (accounts.data ?? []).filter(canPost);
  const picked = postable.filter((account) => chosen.has(account.id));
  const { drafts, change, rewrite, rewriting, failed, writing } = usePostDrafts(
    clip,
    platformsOf(postable),
    postable,
  );
  const problem = postProblem(picked, drafts) ?? whenProblem(mode, at, bulk);

  function toggle(id: number) {
    const next = new Set(chosen);
    if (!next.delete(id)) next.add(id);
    setChosen(next);
  }

  function submit() {
    const targets = targetsOf(picked, drafts);
    let when: When | null = { kind: "now" };
    if (mode === "at") {
      const moment = futureTime(at);
      when = moment ? { kind: "at", at: moment } : null;
    } else if (mode === "bulk") {
      const body = bulkBody([clip.id], targets, bulk);
      when = body ? { kind: "bulk", body } : null;
    }
    if (!when) return;
    send.mutate(
      { targets, when, thumbnailAssetId: cover?.id ?? null },
      {
        onSuccess: (posts) => {
          toast.success(sentLine(mode, posts));
          onClose();
        },
      },
    );
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-[calc(100%-2rem)] max-w-4xl -translate-x-1/2 -translate-y-1/2 flex-col gap-5 overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-popover">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <Dialog.Title className="text-lg font-semibold">
                Schedule post
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
          <div className="grid gap-6 md:grid-cols-[14rem_1fr]">
            <PostAccounts
              accounts={postable}
              loading={accounts.isPending}
              chosen={chosen}
              onToggle={toggle}
            />
            <PostTexts
              platforms={platformsOf(picked)}
              drafts={drafts}
              onChange={change}
              thumbnailUrl={
                cover
                  ? coverUrl(cover.id)
                  : apiUrl(`/media/${clip.project_id}/thumbnail`)
              }
              writing={writing}
              failed={failed}
              rewriting={rewriting}
              onRewrite={rewrite}
            />
          </div>
          <PostCover clip={clip} cover={cover} onCover={setCover} />
          <PostWhen
            mode={mode}
            onModeChange={setMode}
            at={at}
            onAtChange={setAt}
            bulk={bulk}
            onBulkChange={setBulk}
            problem={problem}
            busy={send.isPending}
            onSubmit={submit}
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
