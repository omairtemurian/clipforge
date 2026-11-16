import {
  CircleNotchIcon,
  PaperPlaneTiltIcon,
  XIcon,
} from "@phosphor-icons/react";
import { Dialog } from "radix-ui";
import { useState } from "react";
import { useAccounts } from "@/api/accounts";
import { useBulkSchedule } from "@/api/posts";
import { BulkClipPicker } from "@/components/calendar/BulkClipPicker";
import { PostAccounts } from "@/components/posts/PostAccounts";
import { PostFieldsForm } from "@/components/posts/PostFieldsForm";
import { BulkRules } from "@/components/posts/PostWhen";
import { Button } from "@/components/ui/button";
import {
  blankDrafts,
  bulkProblem,
  bulkTargets,
  postCountLabel,
} from "@/lib/bulkSchedule";
import { platformLabel } from "@/lib/platforms";
import {
  DEFAULT_BULK,
  bulkBody,
  canPost,
  platformsOf,
  scheduledLine,
  whenProblem,
  type PostPlatform,
} from "@/lib/postForm";
import { toast } from "@/lib/toast";

const TAB =
  "rounded-md px-3 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground aria-selected:bg-muted aria-selected:text-foreground";

/**
 * The bulk scheduler (SPEC-v2 3.10): clips of a project, the accounts
 * (on several platforms) to post them to, a tab per platform with the
 * text all its posts share (blank: each clip's own), and the slot rules
 * (times of day, posts per day, days to skip, first day). Every clip goes
 * to every account in the account's next free slots.
 */
export function BulkScheduleDialog({ onClose }: { onClose: () => void }) {
  const accounts = useAccounts();
  const schedule = useBulkSchedule();
  const [clips, setClips] = useState<ReadonlySet<number>>(new Set());
  const [chosen, setChosen] = useState<ReadonlySet<number>>(new Set());
  const [drafts, setDrafts] = useState(blankDrafts);
  const [rules, setRules] = useState(DEFAULT_BULK);
  const [tab, setTab] = useState<PostPlatform | null>(null);

  const postable = (accounts.data ?? []).filter(canPost);
  const picked = postable.filter((account) => chosen.has(account.id));
  const platforms = platformsOf(picked);
  const platform = tab && platforms.includes(tab) ? tab : platforms[0];
  const clipIds = [...clips];
  const problem =
    bulkProblem(clipIds, picked, drafts) ?? whenProblem("bulk", "", rules);

  function toggle(id: number) {
    const next = new Set(chosen);
    if (!next.delete(id)) next.add(id);
    setChosen(next);
  }

  function submit() {
    const body = bulkBody(clipIds, bulkTargets(picked, drafts), rules);
    if (!body) return;
    schedule.mutate(body, {
      onSuccess: (posts) => {
        toast.success(scheduledLine(posts));
        onClose();
      },
    });
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-sm" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-[calc(100%-2rem)] max-w-5xl -translate-x-1/2 -translate-y-1/2 flex-col gap-5 overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-popover">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold">
                Bulk schedule
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                Every clip goes to every account, each in the account&apos;s
                next free slot.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Close">
                <XIcon aria-hidden />
              </Button>
            </Dialog.Close>
          </div>
          <div className="grid gap-6 md:grid-cols-[1fr_14rem]">
            <BulkClipPicker chosen={clips} onChange={setClips} />
            <PostAccounts
              accounts={postable}
              loading={accounts.isPending}
              chosen={chosen}
              onToggle={toggle}
            />
          </div>
          {platform ? (
            <section
              aria-label="Text per platform"
              className="flex flex-col gap-3"
            >
              <div role="tablist" aria-label="Platforms" className="flex gap-1">
                {platforms.map((each) => (
                  <button
                    key={each}
                    type="button"
                    role="tab"
                    aria-selected={each === platform}
                    onClick={() => setTab(each)}
                    className={TAB}
                  >
                    {platformLabel(each)}
                  </button>
                ))}
              </div>
              <PostFieldsForm
                platform={platform}
                fields={drafts[platform]}
                onChange={(fields) =>
                  setDrafts((old) => ({ ...old, [platform]: fields }))
                }
                idPrefix="bulk"
                placeholders={{
                  title: "Each clip's own title",
                  caption: "Each clip's own description",
                  hashtags: "Each clip's own hashtags",
                }}
              />
            </section>
          ) : null}
          <div className="flex flex-col gap-4 border-t border-border pt-4">
            <BulkRules bulk={rules} onChange={setRules} />
            <div className="flex flex-wrap items-center justify-end gap-3">
              {problem && (
                <p role="status" className="text-sm text-muted-foreground">
                  {problem}
                </p>
              )}
              <Button
                disabled={problem !== null || schedule.isPending}
                onClick={submit}
              >
                {schedule.isPending ? (
                  <CircleNotchIcon className="animate-spin" aria-hidden />
                ) : (
                  <PaperPlaneTiltIcon aria-hidden />
                )}
                Schedule {postCountLabel(clips.size, picked.length)}
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
