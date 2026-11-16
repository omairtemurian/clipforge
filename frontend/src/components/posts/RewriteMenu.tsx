import { CircleNotchIcon, SparkleIcon } from "@phosphor-icons/react";
import { Popover } from "radix-ui";
import type { RewriteOptions } from "@/api/postCopy";
import { buttonVariants } from "@/components/ui/button";

interface RewriteMenuProps {
  busy: boolean;
  onRewrite: (options: RewriteOptions) => void;
}

interface Group {
  name: string;
  key: keyof RewriteOptions;
  choices: string[];
}

/** The options of the menu: tone and format rewrite the title and
 * description, hashtags only the hashtags. */
const GROUPS: Group[] = [
  {
    name: "Tone",
    key: "tone",
    choices: ["casual", "punchy", "professional", "funny"],
  },
  { name: "Format", key: "format", choices: ["short", "list", "story"] },
  { name: "Hashtags", key: "hashtags", choices: ["more", "fewer", "none"] },
];

const CHOICE =
  "rounded-md border border-border px-2.5 py-1 text-sm capitalize transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 outline-none";

/** The "Rewrite with AI" button of the modal: a menu of tone, format and
 * hashtags; a choice writes only that option's fields again. */
export function RewriteMenu({ busy, onRewrite }: RewriteMenuProps) {
  return (
    <Popover.Root>
      <Popover.Trigger
        disabled={busy}
        className={buttonVariants({ variant: "outline", size: "sm" })}
      >
        {busy ? (
          <CircleNotchIcon className="animate-spin" aria-hidden />
        ) : (
          <SparkleIcon aria-hidden />
        )}
        Rewrite with AI
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          aria-label="Rewrite options"
          className="z-[60] flex w-72 flex-col gap-3 rounded-xl border border-border bg-popover p-4 text-popover-foreground shadow-popover outline-none"
        >
          {GROUPS.map((group) => (
            <div key={group.key} role="group" aria-label={group.name}>
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                {group.name}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {group.choices.map((choice) => (
                  <Popover.Close key={choice} asChild>
                    <button
                      type="button"
                      className={CHOICE}
                      onClick={() =>
                        onRewrite({ [group.key]: choice } as RewriteOptions)
                      }
                    >
                      {choice}
                    </button>
                  </Popover.Close>
                ))}
              </div>
            </div>
          ))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
