import type { ProcessingSettings } from "@/api/types";
import { CaptionsOnlyNote } from "./CaptionsOnlyNote";
import { MultiChoiceChips } from "./ChoiceChips";
import { Field, INPUT } from "./Field";
import { NativeSelect } from "@/components/ui/native-select";
import { LanguageField } from "./LanguageField";
import { NumberStepper } from "./NumberStepper";
import { PanelTabs } from "./PanelTabs";
import { SettingsToggles } from "./SettingsToggles";
import { StyleTabs } from "./StyleTabs";
import { TimeframeField } from "./TimeframeField";
import {
  GENRES,
  LENGTHS,
  MAX_CLIPS,
  MIN_CLIPS,
  timeframeFields,
  timeframeRange,
  toggleLength,
} from "@/lib/processingSettings";
import { cn } from "@/lib/utils";

interface SettingsFieldsProps {
  settings: ProcessingSettings;
  duration: number | null;
  onChange: (patch: Partial<ProcessingSettings>) => void;
  /** False where the settings are not of one video (no SRT or VTT upload). */
  allowSubtitles?: boolean;
}

/** What AI clipping looks for: genre, count, lengths and topics. */
function AiClippingFields({ settings, onChange }: SettingsFieldsProps) {
  return (
    <div className="grid min-w-0 grid-cols-2 gap-x-6 gap-y-5">
      <Field label="Genre" htmlFor="settings-genre">
        <NativeSelect
          id="settings-genre"
          value={settings.genre}
          onChange={(event) =>
            onChange({
              genre: event.target.value as ProcessingSettings["genre"],
            })
          }
          block
        >
          {GENRES.map((genre) => (
            <option key={genre.value} value={genre.value}>
              {genre.label}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field label="Number of clips" htmlFor="settings-clips">
        <NumberStepper
          id="settings-clips"
          value={settings.num_clips}
          min={MIN_CLIPS}
          max={MAX_CLIPS}
          onChange={(num_clips) => onChange({ num_clips })}
        />
      </Field>
      <div className="col-span-2">
        <Field label="Clip length">
          <MultiChoiceChips
            label="Clip length"
            options={LENGTHS}
            value={settings.length_presets}
            onToggle={(preset) =>
              onChange({
                length_presets: toggleLength(settings.length_presets, preset),
              })
            }
          />
        </Field>
      </div>
      <div className="col-span-2">
        <Field label="Find moments about…" htmlFor="settings-keywords">
          <textarea
            id="settings-keywords"
            rows={2}
            value={settings.keyword_prompt ?? ""}
            onChange={(event) =>
              onChange({ keyword_prompt: event.target.value })
            }
            placeholder="Optional. e.g. the story about the lost luggage, every time the guest talks about pricing, or the funniest crowd reactions"
            className={cn(INPUT, "resize-none py-2")}
          />
        </Field>
      </div>
    </div>
  );
}

/**
 * The controls of every processing setting: AI clipping or the whole
 * timeframe as one clip, the speech language, the timeframe, the edits and
 * the look of the clips.
 */
export function SettingsFields({
  settings,
  duration,
  onChange,
  allowSubtitles = true,
}: SettingsFieldsProps) {
  const range = duration !== null ? timeframeRange(settings, duration) : null;

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PanelTabs
        label="Clipping"
        value={settings.clipping}
        onChange={(clipping) => onChange({ clipping })}
        tabs={[
          {
            value: "ai",
            label: "AI clipping",
            content: (
              <AiClippingFields
                settings={settings}
                duration={duration}
                onChange={onChange}
              />
            ),
          },
          {
            value: "captions_only",
            label: "Captions only",
            content: (
              <CaptionsOnlyNote
                length={range ? range[1] - range[0] : null}
                onUseAi={() => onChange({ clipping: "ai" })}
              />
            ),
          },
        ]}
      />
      <div className="grid min-w-0 grid-cols-2 gap-x-6 gap-y-5">
        <LanguageField
          settings={settings}
          onChange={onChange}
          allowSubtitles={allowSubtitles}
        />
      </div>
      {duration !== null && range && duration >= 2 && (
        <TimeframeField
          duration={duration}
          value={range}
          onChange={(next) => onChange(timeframeFields(next, duration))}
        />
      )}
      <SettingsToggles settings={settings} onChange={onChange} />
      <StyleTabs settings={settings} onChange={onChange} />
    </div>
  );
}
