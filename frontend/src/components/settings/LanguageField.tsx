import { useRef, useState } from "react";
import { CircleNotchIcon, FileTextIcon, XIcon } from "@phosphor-icons/react";
import { uploadSubtitles, useSpeechLanguages } from "@/api/sources";
import type { ProcessingSettings } from "@/api/types";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Field } from "./Field";

type LanguagePatch = Pick<ProcessingSettings, "language" | "subtitles_id">;

interface LanguageFieldProps {
  settings: ProcessingSettings;
  onChange: (patch: Partial<LanguagePatch>) => void;
  /** False where the settings are not of one video (no SRT upload). */
  allowSubtitles?: boolean;
}

/**
 * The spoken language (Auto-detect or one Whisper knows) and an optional
 * SRT or VTT file that replaces the transcription: it is uploaded right away and
 * its token goes in subtitles_id.
 */
export function LanguageField({
  settings,
  onChange,
  allowSubtitles = true,
}: LanguageFieldProps) {
  const languages = useSpeechLanguages();
  const fileInput = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  async function upload(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    try {
      const { subtitles_id } = await uploadSubtitles(file);
      setFileName(file.name);
      onChange({ subtitles_id });
    } catch {
      // apiFetch has shown the error as a toast.
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <Field
      label="Speech language"
      htmlFor="settings-language"
      aside={
        !allowSubtitles ? undefined : settings.subtitles_id ? (
          <span className="inline-flex items-center gap-1 text-foreground">
            <FileTextIcon className="size-3.5" aria-hidden />
            <span className="max-w-32 truncate">
              {fileName ?? "Subtitles attached"}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label="Remove subtitles"
              onClick={() => onChange({ subtitles_id: null })}
            >
              <XIcon aria-hidden />
            </Button>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={uploading}
            className="inline-flex items-center gap-1 text-primary-ink underline-offset-2 hover:underline disabled:opacity-60"
          >
            {uploading && (
              <CircleNotchIcon className="size-3 animate-spin" aria-hidden />
            )}
            Upload SRT or VTT (optional)
          </button>
        )
      }
    >
      <NativeSelect
        id="settings-language"
        value={settings.language ?? ""}
        onChange={(event) => onChange({ language: event.target.value || null })}
        block
      >
        <option value="">Auto-detect</option>
        {languages.data?.map((language) => (
          <option key={language.code} value={language.code}>
            {language.name}
          </option>
        ))}
      </NativeSelect>
      <input
        ref={fileInput}
        type="file"
        accept=".srt,.vtt,application/x-subrip,text/vtt,text/plain"
        aria-label="Subtitles file"
        className="hidden"
        onChange={(event) => void upload(event.target.files?.[0])}
      />
    </Field>
  );
}
