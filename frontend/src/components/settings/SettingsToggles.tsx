import type { ProcessingSettings } from "@/api/types";
import { ToggleRow } from "@/components/ui/toggle-row";

interface SettingsTogglesProps {
  settings: ProcessingSettings;
  onChange: (patch: Partial<ProcessingSettings>) => void;
}

/** The on/off edits made to every clip. */
export function SettingsToggles({ settings, onChange }: SettingsTogglesProps) {
  const aiClipping = settings.clipping === "ai";
  const clipAnything = aiClipping && settings.clip_anything;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <ToggleRow
        label="Auto headline"
        hint={
          aiClipping
            ? "A short opening line over the first seconds"
            : "Needs AI clipping to write it"
        }
        checked={aiClipping && settings.auto_headline}
        disabled={!aiClipping}
        onCheckedChange={(auto_headline) => onChange({ auto_headline })}
      />
      <ToggleRow
        label="Clip anything"
        hint={
          aiClipping
            ? "Also find moments without speech: action, cheers, music"
            : "Needs AI clipping to find them"
        }
        checked={clipAnything}
        disabled={!aiClipping}
        onCheckedChange={(clip_anything) => onChange({ clip_anything })}
      />
      <ToggleRow
        label="Auto zoom"
        hint="Punch in on emphasis, new sentences and laughs"
        checked={settings.auto_zoom}
        onCheckedChange={(auto_zoom) => onChange({ auto_zoom })}
      />
      <ToggleRow
        label="Auto cut silences"
        hint={
          clipAnything
            ? "Off with Clip anything: quiet moments may matter"
            : `Jump cuts over pauses longer than ${settings.auto_cut_min_pause_s} s`
        }
        checked={!clipAnything && settings.auto_cut}
        disabled={clipAnything}
        onCheckedChange={(auto_cut) => onChange({ auto_cut })}
      />
      <ToggleRow
        label="Auto color correction"
        hint="Even out dull or flat footage"
        checked={settings.auto_color}
        onCheckedChange={(auto_color) => onChange({ auto_color })}
      />
      <ToggleRow
        label="Remove filler words"
        hint="Cut “um”, “uh” and long pauses from the clips"
        checked={settings.remove_fillers}
        onCheckedChange={(remove_fillers) => onChange({ remove_fillers })}
      />
    </div>
  );
}
