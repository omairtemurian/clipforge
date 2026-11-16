import {
  ArrowSquareOutIcon,
  FilmSlateIcon,
  XIcon,
} from "@phosphor-icons/react";
import { Dialog } from "radix-ui";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useClip } from "@/api/clips";
import { useCancelPost, usePublishPost, useQueuePost } from "@/api/posts";
import type { Post, SocialAccount } from "@/api/types";
import { AccountAvatar } from "@/components/accounts/AccountAvatar";
import { PostReschedule } from "@/components/calendar/PostReschedule";
import { PostStatusPill } from "@/components/calendar/PostStatusPill";
import { PostTextEdit } from "@/components/calendar/PostTextEdit";
import { Button } from "@/components/ui/button";
import { postTime, postTitle } from "@/lib/calendar";
import { isEditable, isPostPlatform } from "@/lib/postEdit";
import { platformLabel } from "@/lib/platforms";
import { toast } from "@/lib/toast";

interface PostEditorProps {
  post: Post;
  account: SocialAccount | undefined;
  onClose: () => void;
}

/** The line that says when the post goes (or went) out. */
function whenLine(post: Post): string {
  const at = postTime(post);
  const time = at
    ? at.toLocaleString(undefined, { dateStyle: "full", timeStyle: "short" })
    : null;
  if (post.status === "published") return time ? `Posted ${time}` : "Posted";
  if (!time) return "Not scheduled yet";
  if (post.status === "skipped") return `Was due ${time}`;
  return post.status === "failed" ? `Tried ${time}` : `Goes out ${time}`;
}

/** Whether "Post now" sends the post again (it failed or was skipped). */
function canRetry(post: Post): boolean {
  return post.status === "failed" || post.status === "skipped";
}

/**
 * The details sheet of a calendar post (SPEC-v2 3.10): account, status and
 * time; for a draft or scheduled post its text (save), "Publish at"
 * (reschedule), "Schedule" for a timed draft and "Cancel post" (asks
 * first); "Post now" for a failed or skipped post; "Open clip" and, once
 * posted, "View post".
 */
export function PostEditor({ post, account, onClose }: PostEditorProps) {
  const clip = useClip(post.clip_id);
  const cancel = useCancelPost();
  const queue = useQueuePost();
  const publish = usePublishPost();
  const [confirming, setConfirming] = useState(false);
  const editable = isEditable(post);
  const platform = post.platform;

  function cancelPost() {
    cancel.mutate(post.id, {
      onSuccess: () => {
        toast.success("Post canceled.");
        onClose();
      },
    });
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col gap-5 overflow-y-auto border-l border-border bg-card p-6 shadow-popover">
          <div className="flex items-start gap-3">
            <AccountAvatar account={account} platform={platform} badge />
            <div className="min-w-0 flex-1">
              <Dialog.Title className="truncate text-section">
                {postTitle(post)}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-body text-muted-foreground">
                {account?.display_name ?? "Disconnected account"} ·{" "}
                {platformLabel(platform)}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Close">
                <XIcon aria-hidden />
              </Button>
            </Dialog.Close>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <PostStatusPill status={post.status} />
            <span className="text-body">{whenLine(post)}</span>
          </div>
          {post.error && canRetry(post) && (
            <p role="alert" className="text-body text-destructive">
              {post.error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" asChild>
              <Link to={`/clips/${post.clip_id}`}>
                <FilmSlateIcon aria-hidden />
                Open clip
              </Link>
            </Button>
            {canRetry(post) && (
              <Button
                disabled={publish.isPending}
                onClick={() =>
                  publish.mutate(post, {
                    onSuccess: () => {
                      toast.success("Posting now.");
                      onClose();
                    },
                  })
                }
              >
                Post now
              </Button>
            )}
            {post.url && (
              <Button variant="outline" asChild>
                <a href={post.url} target="_blank" rel="noreferrer">
                  <ArrowSquareOutIcon aria-hidden />
                  View post
                </a>
              </Button>
            )}
          </div>
          {editable && (
            <PostReschedule key={post.scheduled_at ?? "none"} post={post} />
          )}
          {editable && isPostPlatform(platform) && clip.data && (
            <PostTextEdit
              key={JSON.stringify(post.payload.text ?? null)}
              post={post}
              platform={platform}
              clip={clip.data}
            />
          )}
          {editable && (
            <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-border pt-4">
              {post.status === "draft" && post.scheduled_at && (
                <Button
                  disabled={queue.isPending}
                  onClick={() =>
                    queue.mutate(post, {
                      onSuccess: () => toast.success("Post scheduled."),
                    })
                  }
                >
                  Schedule post
                </Button>
              )}
              {confirming ? (
                <>
                  <span className="text-body">
                    Cancel this post? It will not go out.
                  </span>
                  <Button variant="ghost" onClick={() => setConfirming(false)}>
                    Keep
                  </Button>
                  <Button
                    variant="destructive"
                    disabled={cancel.isPending}
                    onClick={cancelPost}
                  >
                    Yes, cancel post
                  </Button>
                </>
              ) : (
                <Button
                  variant="destructive"
                  className="ml-auto"
                  onClick={() => setConfirming(true)}
                >
                  Cancel post
                </Button>
              )}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
