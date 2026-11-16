/**
 * The "Schedule post" modal's form (SPEC-v2 3.10): what a post says on
 * each platform, the API bodies made from it (POST /clips/{id}/posts,
 * POST /posts/bulk-schedule) and what still keeps it from being posted.
 */
import type {
  BulkSchedule,
  Clip,
  Post,
  PostTarget,
  PostText,
  ScheduleRules,
  SocialAccount,
} from "@/api/types";
import { formatHashtags, parseHashtags } from "@/lib/clipText";
import type { SocialPlatform } from "@/lib/platforms";

/** The platforms the modal can post to, in tab order. */
export const POST_PLATFORMS = [
  "youtube",
  "tiktok",
  "instagram",
  "facebook",
] as const satisfies readonly SocialPlatform[];
export type PostPlatform = (typeof POST_PLATFORMS)[number];

/** The platforms whose post has a title of its own; the others carry it in
 * the caption. */
const TITLED: ReadonlySet<SocialPlatform> = new Set(["youtube", "facebook"]);

interface Choice {
  value: string;
  label: string;
}

/** Who can see a post, per platform. TikTok has no default (its content
 * sharing guidelines); Instagram and Facebook posts are public. */
export const PRIVACY_CHOICES: Record<PostPlatform, Choice[]> = {
  youtube: [
    { value: "public", label: "Public" },
    { value: "unlisted", label: "Unlisted" },
    { value: "private", label: "Private" },
  ],
  tiktok: [
    { value: "PUBLIC_TO_EVERYONE", label: "Everyone" },
    { value: "MUTUAL_FOLLOW_FRIENDS", label: "Friends" },
    { value: "FOLLOWER_OF_CREATOR", label: "Followers" },
    { value: "SELF_ONLY", label: "Only me" },
  ],
  instagram: [{ value: "public", label: "Public" }],
  facebook: [{ value: "public", label: "Public" }],
};

/** What a post says on one platform, as typed in the form. */
export interface PostFields {
  title: string;
  caption: string;
  hashtags: string;
  privacy: string;
}

export type PostDrafts = Record<PostPlatform, PostFields>;

/** Whether the platform's post has a title field. */
export function hasTitle(platform: SocialPlatform): boolean {
  return TITLED.has(platform);
}

/** Whether the modal can post to the account's platform. */
export function canPost(account: SocialAccount): boolean {
  return (POST_PLATFORMS as readonly string[]).includes(account.platform);
}

/** The fields of a platform's post filled from the clip's own texts; a
 * platform without titles starts with the title above the description. */
export function fieldsOf(
  platform: PostPlatform,
  texts: Pick<Clip, "title" | "description" | "hashtags">,
): PostFields {
  const titled = hasTitle(platform);
  const caption = titled
    ? texts.description
    : [texts.title, texts.description]
        .filter((part) => part.trim())
        .join("\n\n");
  return {
    title: titled ? texts.title : "",
    caption,
    hashtags: formatHashtags(texts.hashtags),
    privacy: platform === "tiktok" ? "" : PRIVACY_CHOICES[platform][0].value,
  };
}

/** Every platform's fields filled from the clip. */
export function draftsOf(
  texts: Pick<Clip, "title" | "description" | "hashtags">,
): PostDrafts {
  const entries = POST_PLATFORMS.map((p) => [p, fieldsOf(p, texts)] as const);
  return Object.fromEntries(entries) as PostDrafts;
}

/** The PostText the API takes for fields on platform. */
export function postText(platform: PostPlatform, fields: PostFields): PostText {
  return {
    title: hasTitle(platform) ? fields.title.trim() : "",
    caption: fields.caption,
    hashtags: parseHashtags(fields.hashtags),
    link: null,
    privacy: fields.privacy || null,
    collaborators: [],
    options: {},
  };
}

/** A target per chosen account, saying what its platform's fields say. */
export function targetsOf(
  accounts: SocialAccount[],
  drafts: PostDrafts,
): PostTarget[] {
  return accounts.filter(canPost).map((account) => {
    const platform = account.platform as PostPlatform;
    return {
      account_id: account.id,
      text: postText(platform, drafts[platform]),
    };
  });
}

/** The platforms of the chosen accounts, in tab order. */
export function platformsOf(accounts: SocialAccount[]): PostPlatform[] {
  return POST_PLATFORMS.filter((platform) =>
    accounts.some((account) => account.platform === platform),
  );
}

/** The id of the account whose always-included hashtags a platform's text
 * gets: the platform's default account among accounts, else its first. */
export function accountFor(
  accounts: SocialAccount[],
  platform: PostPlatform,
): number | null {
  const own = accounts.filter((account) => account.platform === platform);
  return (own.find((account) => account.is_default) ?? own[0])?.id ?? null;
}

/** What keeps the chosen accounts' posts from going out, or null. */
export function postProblem(
  accounts: SocialAccount[],
  drafts: PostDrafts,
): string | null {
  if (accounts.length === 0) return "Choose an account to post to.";
  const platforms = platformsOf(accounts);
  if (platforms.includes("youtube") && !drafts.youtube.title.trim()) {
    return "The YouTube video needs a title.";
  }
  if (platforms.includes("tiktok") && !drafts.tiktok.privacy) {
    return "Choose who can see the TikTok post.";
  }
  return null;
}

/** The simple bulk rules of the form: the times of day, posts per day,
 * the days to skip and the first day (yyyy-mm-dd, "" for today). */
export interface BulkFields {
  times: string;
  postsPerDay: number;
  skipDays: ScheduleRules["skip_days"];
  startDate: string;
}

export const DEFAULT_BULK: BulkFields = {
  times: "09:00, 18:00",
  postsPerDay: 1,
  skipDays: [],
  startDate: "",
};

/** The "HH:MM" times typed in text, sorted, without repeats. */
export function parseTimes(text: string): string[] {
  const times = text
    .split(/[\s,]+/)
    .filter((time) => /^([01]\d|2[0-3]):[0-5]\d$/.test(time));
  return [...new Set(times)].sort();
}

/** The body of POST /posts/bulk-schedule for the clips on targets, in the
 * browser's timezone; null while no valid time is typed or there is no
 * clip or target. */
export function bulkBody(
  clipIds: number[],
  targets: PostTarget[],
  fields: BulkFields,
  timezone = Intl.DateTimeFormat().resolvedOptions().timeZone,
): BulkSchedule | null {
  const times = parseTimes(fields.times);
  if (times.length === 0 || targets.length === 0 || clipIds.length === 0) {
    return null;
  }
  return {
    clip_ids: clipIds as BulkSchedule["clip_ids"],
    targets: targets as BulkSchedule["targets"],
    rules: {
      timezone,
      times: times as ScheduleRules["times"],
      posts_per_day: fields.postsPerDay,
      skip_days: fields.skipDays,
      start_date: fields.startDate || null,
    },
    queue: true,
  };
}

/** The ISO time of a datetime-local value, or null unless it is later than
 * now. */
export function futureTime(local: string, now = new Date()): string | null {
  if (!local) return null;
  const moment = new Date(local);
  if (Number.isNaN(moment.getTime()) || moment <= now) return null;
  return moment.toISOString();
}

/** When the posts go out: now, at a picked time or in free slots. */
export type WhenMode = "now" | "at" | "bulk";

/** What keeps the posts from going out in mode, or null. */
export function whenProblem(
  mode: WhenMode,
  at: string,
  bulk: BulkFields,
  now = new Date(),
): string | null {
  if (mode === "at" && futureTime(at, now) === null) {
    return "Pick a time later than now.";
  }
  if (mode === "bulk" && parseTimes(bulk.times).length === 0) {
    return "Type a time of day such as 09:00.";
  }
  return null;
}

/** The toast after posts were scheduled: how many and the first time. */
export function scheduledLine(posts: Post[]): string {
  const count = posts.length === 1 ? "1 post" : `${posts.length} posts`;
  const first = posts
    .map((post) => post.scheduled_at)
    .filter((at): at is string => at !== null)
    .sort()[0];
  const when = first
    ? `, the first on ${new Date(first).toLocaleString()}`
    : "";
  return `Scheduled ${count}${when}.`;
}
