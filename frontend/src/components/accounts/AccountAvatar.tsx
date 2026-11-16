import {
  FacebookLogoIcon,
  InstagramLogoIcon,
  LinkedinLogoIcon,
  TiktokLogoIcon,
  XLogoIcon,
  YoutubeLogoIcon,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { useState } from "react";
import type { SocialAccount } from "@/api/types";
import { platformLabel, type SocialPlatform } from "@/lib/platforms";
import { cn } from "@/lib/utils";

const PLATFORM_ICONS: Record<SocialPlatform, Icon> = {
  youtube: YoutubeLogoIcon,
  tiktok: TiktokLogoIcon,
  instagram: InstagramLogoIcon,
  facebook: FacebookLogoIcon,
  x: XLogoIcon,
  linkedin: LinkedinLogoIcon,
};

const SIZES = {
  sm: "size-7 text-caption",
  md: "size-9 text-body",
} as const;

interface AccountAvatarProps {
  /** The account; undefined once it was disconnected. */
  account: SocialAccount | undefined;
  platform: SocialPlatform;
  size?: keyof typeof SIZES;
  /** A small platform logo on the bottom right. */
  badge?: boolean;
}

/** An account's picture (or its platform's initial), optionally with a
 * small platform badge. */
export function AccountAvatar({
  account,
  platform,
  size = "md",
  badge = false,
}: AccountAvatarProps) {
  const [broken, setBroken] = useState(false);
  const PlatformIcon = PLATFORM_ICONS[platform];
  const box = cn(
    "flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/15 font-semibold text-primary-ink",
    SIZES[size],
  );
  const picture =
    account?.avatar_url && !broken ? (
      <span className={box}>
        <img
          src={account.avatar_url}
          alt={`${account.display_name}'s profile picture`}
          referrerPolicy="no-referrer"
          onError={() => setBroken(true)}
          className="size-full object-cover"
        />
      </span>
    ) : (
      <span aria-hidden className={box}>
        {platformLabel(platform).charAt(0)}
      </span>
    );
  if (!badge) return picture;
  return (
    <span className="relative inline-flex shrink-0">
      {picture}
      <span
        aria-label={platformLabel(platform)}
        role="img"
        className="absolute -right-1 -bottom-1 flex size-4 items-center justify-center rounded-full bg-foreground text-background ring-2 ring-card"
      >
        <PlatformIcon weight="fill" className="size-2.5" aria-hidden />
      </span>
    </span>
  );
}
