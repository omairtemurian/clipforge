import { useRef, useState } from "react";
import { CircleNotchIcon, FileTextIcon, XIcon } from "@phosphor-icons/react";
import { uploadSubtitles } from "@/api/sources";
import { Button } from "@/components/ui/button";

/** An uploaded SRT or VTT: its token and the name of the file. */
export interface AttachedSubtitles {
  id: string;
  name: string;
}

interface SubtitlesButtonProps {
  value: AttachedSubtitles | null;
  onChange: (value: AttachedSubtitles | null) => void;
}

/**
 * The Subtitles button of Home: uploads an SRT or VTT file right away, and
 * shows its name with a remove button once it is attached. The next project
 * uses it as the transcript instead of Whisper.
 */
export function SubtitlesButton({ value, onChange }: SubtitlesButtonProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function upload(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    try {
      const { subtitles_id } = await uploadSubtitles(file);
      onChange({ id: subtitles_id, name: file.name });
    } catch {
      // apiFetch has shown the error as a toast.
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <>
      {value ? (
        <span className="inline-flex h-8 items-center gap-1 px-2.5 text-body">
          <FileTextIcon className="size-4" aria-hidden />
          <span className="max-w-40 truncate">{value.name}</span>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label="Remove subtitles"
            onClick={() => onChange(null)}
          >
            <XIcon aria-hidden />
          </Button>
        </span>
      ) : (
        <Button
          type="button"
          variant="ghost"
          disabled={uploading}
          onClick={() => fileInput.current?.click()}
        >
          {uploading ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <FileTextIcon aria-hidden />
          )}
          Subtitles
        </Button>
      )}
      <input
        ref={fileInput}
        type="file"
        accept=".srt,.vtt,application/x-subrip,text/vtt,text/plain"
        aria-label="Upload a subtitles file"
        className="hidden"
        onChange={(event) => void upload(event.target.files?.[0])}
      />
    </>
  );
}
