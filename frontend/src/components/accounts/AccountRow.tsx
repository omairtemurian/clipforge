import { StarIcon, TrashIcon } from "@phosphor-icons/react";
import { useState } from "react";
import {
  useDisconnectAccount,
  useSetAccountHashtags,
  useSetDefaultAccount,
} from "@/api/accounts";
import type { SocialAccount } from "@/api/types";
import { HashtagChips } from "@/components/settings/HashtagChips";
import { Button } from "@/components/ui/button";
import { platformLabel } from "@/lib/platforms";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";
import { Pill } from "@/components/ui/pill";
import { AccountAvatar } from "./AccountAvatar";

/** One connected account: platform, name, when it was connected, the
 * platform's restrictions as badges, and Remove (asks first). */
export function AccountRow({ account }: { account: SocialAccount }) {
  const [confirming, setConfirming] = useState(false);
  const disconnect = useDisconnectAccount();
  const setDefault = useSetDefaultAccount();
  const setHashtags = useSetAccountHashtags();
  const platform = platformLabel(account.platform);
  const label = `${account.display_name} (${platform})`;

  return (
    <li
      aria-label={label}
      className={cn(cardClass(), "flex flex-col gap-3 p-4")}
    >
      <div className="flex flex-wrap items-center gap-3">
        <AccountAvatar account={account} platform={account.platform} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">
            <span className="font-normal text-muted-foreground">
              Connected as{" "}
            </span>
            {account.display_name}
          </p>
          <p className="text-caption text-muted-foreground">
            {platform} · connected{" "}
            {new Date(account.connected_at).toLocaleDateString()}
          </p>
        </div>
        <Button
          variant={account.is_default ? "secondary" : "ghost"}
          size="sm"
          aria-pressed={account.is_default}
          aria-label={
            account.is_default
              ? `${label} is the default account`
              : `Make ${label} the default account`
          }
          title={
            account.is_default
              ? `The default ${platform} account of one-click posts`
              : `Use for one-click ${platform} posts`
          }
          disabled={account.is_default || setDefault.isPending}
          onClick={() => setDefault.mutate(account.id)}
        >
          <StarIcon
            aria-hidden
            weight={account.is_default ? "fill" : "regular"}
          />
          {account.is_default ? "Default" : "Make default"}
        </Button>
        {confirming ? (
          <div className="flex items-center gap-2">
            <Button
              variant="destructive"
              size="sm"
              disabled={disconnect.isPending}
              onClick={() =>
                disconnect.mutate(account.id, {
                  onSettled: () => setConfirming(false),
                })
              }
            >
              Remove {account.display_name}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirming(false)}
            >
              Keep
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            aria-label={`Remove ${label}`}
            onClick={() => setConfirming(true)}
          >
            <TrashIcon aria-hidden />
            Remove
          </Button>
        )}
      </div>
      <HashtagChips
        label={`Always include for ${label}`}
        value={account.always_hashtags}
        disabled={setHashtags.isPending}
        onChange={(hashtags) =>
          setHashtags.mutate({ id: account.id, hashtags })
        }
        hint="Added to this account's posts, next to the ones in Settings."
      />
      {account.restrictions.length > 0 && (
        <ul
          aria-label={`Restrictions of ${account.display_name}`}
          className="flex flex-wrap gap-2"
        >
          {account.restrictions.map((restriction) => (
            <li key={restriction}>
              <Pill tone="warning" className="whitespace-normal">
                {restriction}
              </Pill>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
