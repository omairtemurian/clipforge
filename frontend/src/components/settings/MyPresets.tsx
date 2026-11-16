import { useState, type KeyboardEvent } from "react";
import {
  BookmarkSimpleIcon,
  CircleNotchIcon,
  TrashIcon,
} from "@phosphor-icons/react";
import {
  useDeletePreset,
  useProcessingPresets,
  useSavePreset,
} from "@/api/presets";
import type { ProcessingSettings } from "@/api/types";
import { Button } from "@/components/ui/button";
import { INPUT } from "./Field";
import { cn } from "@/lib/utils";

const NAME_MAX = 60;

interface MyPresetsProps {
  settings: ProcessingSettings;
  /** Called with a saved preset's settings (no timeframe or subtitles). */
  onApply: (settings: ProcessingSettings) => void;
}

/** The owner's named presets: save the whole panel, apply or delete one. */
export function MyPresets({ settings, onApply }: MyPresetsProps) {
  const presets = useProcessingPresets();
  const save = useSavePreset();
  const remove = useDeletePreset();
  const [name, setName] = useState("");
  const trimmed = name.trim();

  function submit() {
    if (!trimmed || save.isPending) return;
    save.mutate({ name: trimmed, settings }, { onSuccess: () => setName("") });
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    submit();
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <input
          type="text"
          aria-label="Preset name"
          maxLength={NAME_MAX}
          value={name}
          onChange={(event) => setName(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Name these settings, e.g. Weekly podcast"
          className={cn(INPUT, "h-9")}
        />
        <Button
          type="button"
          variant="outline"
          disabled={!trimmed || save.isPending}
          onClick={submit}
        >
          {save.isPending ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <BookmarkSimpleIcon aria-hidden />
          )}
          Save preset
        </Button>
      </div>
      {presets.data?.length ? (
        <ul aria-label="My presets" className="flex flex-col gap-2">
          {presets.data.map((preset) => (
            <li
              key={preset.name}
              className="flex items-center gap-2 rounded-lg border border-border py-1 pr-1 pl-3"
            >
              <span className="min-w-0 flex-1 truncate text-body">
                {preset.name}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Apply ${preset.name}`}
                onClick={() => onApply(preset.settings)}
              >
                Apply
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Delete ${preset.name}`}
                disabled={remove.isPending}
                onClick={() => remove.mutate(preset.name)}
              >
                <TrashIcon aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-muted-foreground">
          {presets.isLoading
            ? "Loading your presets…"
            : "No presets yet. Save the settings above to reuse them on the next video."}
        </p>
      )}
    </div>
  );
}
