import { useId } from "react";
import { Field } from "@/components/settings/Field";
import { NativeSelect } from "@/components/ui/native-select";
import { backendLabel, type TranscribeBackend } from "@/lib/settingsForm";
import { Section } from "./Section";
import { TextSetting } from "./TextSetting";
import type { SectionProps } from "./sectionProps";

const BACKENDS: { value: TranscribeBackend; label: string }[] = [
  { value: "auto", label: "Automatic" },
  { value: "mlx", label: "Apple GPU (MLX)" },
  { value: "faster_whisper", label: "CPU (faster-whisper)" },
];

interface DefaultsSectionProps extends SectionProps {
  /** The backend setting being edited, and the one that runs on this machine. */
  backend: TranscribeBackend;
  activeBackend: "faster_whisper" | "mlx";
  onBackend: (backend: TranscribeBackend) => void;
}

/** Transcription, the credit line and the tool and download settings. */
export function DefaultsSection({
  draft,
  problems,
  onText,
  backend,
  activeBackend,
  onBackend,
}: DefaultsSectionProps) {
  const backendId = useId();
  const text = (field: keyof typeof draft.text) => ({
    value: draft.text[field],
    error: problems[field],
    onChange: (value: string) => onText(field, value),
  });
  return (
    <>
      <Section
        title="Transcription"
        description="The speech-to-text model that reads each video."
      >
        <TextSetting
          label="Whisper model"
          hint="A model size such as small or medium, or a Hugging Face repo id."
          {...text("whisper_model")}
        />
        <Field label="Transcription engine" htmlFor={backendId}>
          <NativeSelect
            id={backendId}
            value={backend}
            aria-describedby={`${backendId}-hint`}
            onChange={(event) =>
              onBackend(event.target.value as TranscribeBackend)
            }
            block
          >
            {BACKENDS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
          <p
            id={`${backendId}-hint`}
            className="text-caption text-muted-foreground"
          >
            Running on:{" "}
            <strong className="text-foreground">
              {backendLabel(activeBackend)}
            </strong>
            . Automatic uses the Mac's GPU when MLX Whisper and its model are
            installed (run make setup), and the CPU otherwise.
          </p>
        </Field>
      </Section>
      <Section
        title="Credit line"
        description="Added to each clip's description so viewers find the source."
      >
        <TextSetting
          label="Credit template"
          hint="Fields you can use: {channel}, {channel_url}, {title}."
          {...text("credit_template")}
        />
      </Section>
      <Section
        title="Tools and downloads"
        description="Leave blank to use the defaults."
      >
        <TextSetting
          label="ffmpeg path"
          placeholder="Default"
          {...text("ffmpeg_bin")}
        />
        <TextSetting
          label="ffprobe path"
          placeholder="Default"
          {...text("ffprobe_bin")}
        />
        <TextSetting
          label="Cookies from browser"
          hint="For videos that need a sign-in, e.g. chrome or chrome:Profile 1."
          placeholder="None"
          {...text("ytdlp_cookies_from_browser")}
        />
        <TextSetting
          label="Cookies file"
          hint="A cookies.txt file, as another way to sign in."
          placeholder="None"
          {...text("ytdlp_cookies_file")}
        />
      </Section>
    </>
  );
}
