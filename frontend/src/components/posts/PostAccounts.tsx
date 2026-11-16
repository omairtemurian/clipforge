import { PlusIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { SocialAccount } from "@/api/types";
import { platformLabel } from "@/lib/platforms";
import { platformsOf, type PostPlatform } from "@/lib/postForm";
import { cn } from "@/lib/utils";

interface PostAccountsProps {
  accounts: SocialAccount[];
  loading: boolean;
  chosen: ReadonlySet<number>;
  onToggle: (id: number) => void;
}

const CHIP =
  "rounded-full border border-border px-2.5 py-0.5 text-xs transition-colors hover:bg-muted aria-pressed:border-primary aria-pressed:bg-primary/15 aria-pressed:text-foreground";

/** The modal's left column: the connected accounts to post to (filter by
 * platform), each with a checkbox, and "Add account". */
export function PostAccounts({
  accounts,
  loading,
  chosen,
  onToggle,
}: PostAccountsProps) {
  const [filter, setFilter] = useState<PostPlatform | "all">("all");
  const platforms = platformsOf(accounts);
  const shown = accounts.filter(
    (account) => filter === "all" || account.platform === filter,
  );

  return (
    <section
      aria-labelledby="post-accounts"
      className="flex min-w-0 flex-col gap-3"
    >
      <h3 id="post-accounts" className="text-sm font-medium">
        Post to
      </h3>
      {platforms.length > 1 && (
        <div
          role="group"
          aria-label="Filter accounts"
          className="flex flex-wrap gap-1.5"
        >
          {(["all", ...platforms] as const).map((platform) => (
            <button
              key={platform}
              type="button"
              aria-pressed={filter === platform}
              onClick={() => setFilter(platform)}
              className={CHIP}
            >
              {platform === "all" ? "All" : platformLabel(platform)}
            </button>
          ))}
        </div>
      )}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading accounts…</p>
      ) : accounts.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No account connected yet. Connect one to publish this clip.
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {shown.map((account) => (
            <li key={account.id}>
              <label
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-lg border border-transparent px-2 py-1.5 hover:bg-muted",
                  chosen.has(account.id) && "border-border bg-muted/60",
                )}
              >
                <input
                  type="checkbox"
                  checked={chosen.has(account.id)}
                  onChange={() => onToggle(account.id)}
                  className="size-4 accent-primary"
                />
                <span className="flex min-w-0 flex-col">
                  <span className="truncate text-sm">
                    {account.display_name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {platformLabel(account.platform)}
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      <Link
        to="/accounts"
        className="inline-flex items-center gap-1.5 self-start text-sm text-primary-ink hover:underline"
      >
        <PlusIcon className="size-4" aria-hidden />
        Add account
      </Link>
    </section>
  );
}
