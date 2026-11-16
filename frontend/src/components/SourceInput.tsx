import { useRef, useState, type FormEvent } from "react";
import {
  HardDriveIcon,
  LinkSimpleIcon,
  UploadSimpleIcon,
} from "@phosphor-icons/react";
import { DriveImportDialog } from "@/components/DriveImportDialog";
import {
  SubtitlesButton,
  type AttachedSubtitles,
} from "@/components/SubtitlesButton";
import { ToolChips, type ClippingMode } from "@/components/ToolChips";
import { Button } from "@/components/ui/button";
import { checkVideoUrl, firstVideoFile } from "@/lib/videoSource";
import type { VideoSource } from "@/api/projects";

interface SourceInputProps {
  onSubmit: (source: VideoSource) => void;
  mode: ClippingMode;
  onModeChange: (mode: ClippingMode) => void;
  subtitles: AttachedSubtitles | null;
  onSubtitlesChange: (subtitles: AttachedSubtitles | null) => void;
}

/** The pill where a video link is pasted, the Upload, Google Drive and
 * Subtitles buttons, and the chips that choose the clipping mode. */
export function SourceInput({
  onSubmit,
  mode,
  onModeChange,
  subtitles,
  onSubtitlesChange,
}: SourceInputProps) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [driveOpen, setDriveOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const checked = checkVideoUrl(text);
    if (!checked.ok) {
      setError(checked.message);
      return;
    }
    setError(null);
    setText("");
    onSubmit({ url: checked.url });
  }

  function pickFile(files: FileList | null) {
    const file = firstVideoFile(files ?? []);
    if (file) {
      setError(null);
      onSubmit({ file });
    } else if (files?.length) {
      setError("That file is not a video.");
    }
    if (fileInput.current) fileInput.current.value = "";
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <form
        onSubmit={submit}
        noValidate
        className="flex items-center gap-3 rounded-full border border-border bg-card p-2 pl-6 shadow-card transition-[border-color,box-shadow] focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30 hover:border-foreground/20"
      >
        <LinkSimpleIcon
          className="size-5 shrink-0 text-muted-foreground"
          aria-hidden
        />
        <input
          type="text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Drop a YouTube link"
          aria-label="Video link"
          aria-invalid={error !== null}
          aria-describedby={error ? "source-error" : undefined}
          className="h-12 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground"
        />
        <Button
          type="submit"
          size="lg"
          className="h-12 rounded-full px-6 text-base font-semibold"
        >
          Get clips
        </Button>
      </form>
      {error && (
        <p
          id="source-error"
          role="alert"
          className="mt-2 text-center text-body text-destructive"
        >
          {error}
        </p>
      )}
      <div className="mt-4 flex items-center justify-center gap-2">
        <Button
          type="button"
          variant="ghost"
          onClick={() => fileInput.current?.click()}
        >
          <UploadSimpleIcon aria-hidden />
          Upload
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => setDriveOpen(true)}
        >
          <HardDriveIcon aria-hidden />
          Google Drive
        </Button>
        <SubtitlesButton value={subtitles} onChange={onSubtitlesChange} />
        <input
          ref={fileInput}
          type="file"
          accept="video/*,.mkv,.mov,.mp4,.webm"
          aria-label="Upload a video file"
          className="hidden"
          onChange={(event) => pickFile(event.target.files)}
        />
      </div>
      {driveOpen && (
        <DriveImportDialog
          onChoose={(drive) => {
            setDriveOpen(false);
            setError(null);
            onSubmit({ drive });
          }}
          onClose={() => setDriveOpen(false)}
        />
      )}
      <ToolChips mode={mode} onModeChange={onModeChange} />
    </div>
  );
}
