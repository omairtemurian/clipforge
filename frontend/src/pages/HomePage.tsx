import { useState } from "react";
import { CloudArrowUpIcon } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { useAddProject, type VideoSource } from "@/api/projects";
import type { ProcessingSettings } from "@/api/types";
import { RecentProjects } from "@/components/RecentProjects";
import { SettingsPanel } from "@/components/SettingsPanel";
import { SourceInput } from "@/components/SourceInput";
import type { AttachedSubtitles } from "@/components/SubtitlesButton";
import type { ClippingMode } from "@/components/ToolChips";
import type { RightsChoice } from "@/lib/sourceRights";
import { toast } from "@/lib/toast";
import { useFileDrop } from "@/lib/useFileDrop";
import { firstVideoFile } from "@/lib/videoSource";
import { projectPath } from "@/components/navigation";

/** The video in the settings panel; a new key resets the panel. */
interface Chosen {
  source: VideoSource;
  key: number;
}

/**
 * Home: paste a link, drop a video or attach subtitles, choose the settings in the panel that
 * opens, then "Get clips" creates the project and opens it.
 */
export function HomePage() {
  const add = useAddProject();
  const navigate = useNavigate();
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [mode, setMode] = useState<ClippingMode>("ai");
  const [subtitles, setSubtitles] = useState<AttachedSubtitles | null>(null);

  function choose(source: VideoSource) {
    setChosen((previous) => ({ source, key: (previous?.key ?? 0) + 1 }));
  }

  function create(settings: ProcessingSettings, rights: RightsChoice) {
    if (!chosen || add.isPending) return;
    add.mutate(
      {
        source: chosen.source,
        settings,
        rights,
        onUploadProgress: setUploadProgress,
      },
      {
        onSuccess: (project) => {
          setSubtitles(null);
          navigate(projectPath(project.id));
        },
        onSettled: () => setUploadProgress(null),
      },
    );
  }

  const dragging = useFileDrop((files) => {
    const file = firstVideoFile(files);
    if (file) choose({ file });
    else toast.error("Drop a video file (mp4, mov, mkv, webm).");
  });

  return (
    <div className="mx-auto w-full max-w-wide px-page pt-24 pb-16">
      <h1 className="sr-only">ClipForge</h1>
      <p className="mb-8 text-center text-display text-balance">
        Turn long videos into <span className="text-primary-ink">shorts</span>
      </p>
      <SourceInput
        onSubmit={choose}
        mode={mode}
        onModeChange={setMode}
        subtitles={subtitles}
        onSubtitlesChange={setSubtitles}
      />
      {chosen && (
        <SettingsPanel
          key={chosen.key}
          source={chosen.source}
          initial={{ clipping: mode, subtitles_id: subtitles?.id ?? null }}
          busy={add.isPending}
          uploadProgress={uploadProgress}
          onSubmit={create}
          onClose={() => setChosen(null)}
        />
      )}
      <RecentProjects />
      {dragging && (
        <div
          role="presentation"
          className="pointer-events-none fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-background/80 backdrop-blur-sm"
        >
          <CloudArrowUpIcon className="size-12 text-primary-ink" aria-hidden />
          <p className="text-lg font-medium">Drop a video to get clips</p>
        </div>
      )}
    </div>
  );
}
