import type { WatchedChannel, WatchedVideo } from "@/api/types";
import { timeAgo } from "@/lib/format";

/** The name of a watched channel: its title once its feed was read, else
 * its id. */
export function channelName(channel: WatchedChannel): string {
  return channel.title || channel.channel_id;
}

/** The link of a channel on YouTube. */
export function channelUrl(channel: WatchedChannel): string {
  return `https://www.youtube.com/channel/${channel.channel_id}`;
}

/**
 * When the channel's feed was last read, in words: "Not checked yet",
 * "Checked just now", "Checked 5 min ago", "Checked 3 h ago" or the date.
 */
export function lastCheckedLabel(
  lastCheckedAt: string | null,
  now: Date = new Date(),
): string {
  const ago = lastCheckedAt === null ? "" : timeAgo(lastCheckedAt, now);
  return ago ? `Checked ${ago}` : "Not checked yet";
}

/** The videos that became projects (the ones already in the feed when the
 * channel was added did not). */
export function importedVideos(videos: WatchedVideo[]): WatchedVideo[] {
  return videos.filter((video) => video.project_id !== null);
}

/** "1 new project" / "3 new projects" / "No new projects yet". */
export function newProjectsLabel(count: number): string {
  if (count === 0) return "No new projects yet";
  return `${count} new ${count === 1 ? "project" : "projects"}`;
}
