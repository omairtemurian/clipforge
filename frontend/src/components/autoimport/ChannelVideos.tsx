import { Link } from "react-router-dom";
import type { WatchedVideo } from "@/api/types";
import { projectPath } from "@/components/navigation";
import { importedVideos } from "@/lib/autoImport";
import { formatDate } from "@/lib/format";

/** The projects that a channel's new videos became, newest first. */
export function ChannelVideos({ videos }: { videos: WatchedVideo[] }) {
  const imported = importedVideos(videos);
  const skipped = videos.length - imported.length;

  if (imported.length === 0)
    return (
      <p className="text-body text-muted-foreground">
        No video has been imported yet.
        {skipped > 0 && ` The ${skipped} already on the channel are skipped.`}
      </p>
    );
  return (
    <ul aria-label="New projects" className="flex flex-col gap-1.5">
      {imported.map((video) => (
        <li
          key={video.video_id}
          className="flex items-baseline justify-between gap-3 text-body"
        >
          <Link
            to={projectPath(video.project_id as number)}
            className="truncate text-primary-ink hover:underline"
          >
            {video.title || video.video_id}
          </Link>
          <span className="shrink-0 text-caption text-muted-foreground">
            {formatDate(video.seen_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}
