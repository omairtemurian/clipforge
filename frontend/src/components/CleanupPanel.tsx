import { EraserIcon, MagnifyingGlassIcon } from "@phosphor-icons/react";
import { useState } from "react";
import {
  useApplyCleanup,
  useFillerLanguages,
  usePreviewCleanup,
} from "@/api/clipCleanup";
import type { CleanupOptions, CleanupPreview, Clip } from "@/api/types";
import { CleanupItems } from "@/components/CleanupItems";
import { EnhanceSection } from "@/components/EnhanceSection";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { Field } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { PanelGroup } from "@/components/ui/panel";
import { ToggleRow } from "@/components/ui/toggle-row";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { PAUSE_DEFAULT_S, PAUSE_MAX_S, PAUSE_MIN_S } from "@/lib/cleanup";

interface CleanupPanelProps {
  clip: Clip;
  edits: ClipEdits;
  /** A save or render is under way. */
  busy: boolean;
}

/**
 * The editor's Cleanup panel (SPEC-v2 3.5): speech cleanup and speech
 * enhancement. Choose what to look for (filler words of a language, pauses
 * longer than a threshold, bad takes the AI finds), then "Find what to
 * remove" lists the items, each with a checkbox; "Remove" cuts the checked
 * ones from the clip (a version: undo takes it back). Below it the
 * enhancement strength. Both act on the saved clip, so they wait for
 * unsaved changes; the clip an answer holds replaces the editor's. The
 * video changes when the clip is rendered again.
 */
export function CleanupPanel({ clip, edits, busy }: CleanupPanelProps) {
  const languages = useFillerLanguages();
  const find = usePreviewCleanup(clip.id);
  const remove = useApplyCleanup(clip.id);
  const [fillers, setFillers] = useState(true);
  const [pauses, setPauses] = useState(true);
  const [badTakes, setBadTakes] = useState(false);
  const [threshold, setThreshold] = useState(PAUSE_DEFAULT_S);
  const [language, setLanguage] = useState("");
  const [preview, setPreview] = useState<CleanupPreview | null>(null);
  const [unchecked, setUnchecked] = useState<ReadonlySet<number>>(new Set());
  const locked = edits.dirty || busy || find.isPending || remove.isPending;

  /** Change an option; what the last search found no longer matches it. */
  const option = <T,>(set: (value: T) => void) => {
    return (value: T) => {
      set(value);
      setPreview(null);
    };
  };

  const search = async () => {
    const options: CleanupOptions = {
      fillers,
      pauses,
      pause_threshold_s: threshold,
      bad_takes: badTakes,
      language: language || null,
    };
    try {
      setPreview(await find.mutateAsync(options));
      setUnchecked(new Set());
    } catch {
      // apiFetch has shown the error
    }
  };
  const toggle = (index: number) => {
    const next = new Set(unchecked);
    if (!next.delete(index)) next.add(index);
    setUnchecked(next);
  };
  const apply = async () => {
    if (!preview) return;
    try {
      edits.reset(
        await remove.mutateAsync({
          items: preview.items,
          unchecked: [...unchecked],
        }),
      );
      setPreview(null);
    } catch {
      // apiFetch has shown the error
    }
  };

  const items = preview?.items ?? [];
  const checked = items.length - unchecked.size;

  return (
    <>
      {(edits.dirty || busy) && (
        <p role="status" className="text-caption text-muted-foreground">
          Cleanup waits until your changes are saved.
        </p>
      )}
      <PanelGroup title="Speech cleanup">
        <ToggleRow
          label="Filler words"
          hint="um, uh, like…"
          checked={fillers}
          onCheckedChange={option(setFillers)}
        />
        {fillers && (
          <Field label="Filler language" htmlFor="cleanup-language">
            <NativeSelect
              block
              id="cleanup-language"
              value={language}
              onChange={(event) => option(setLanguage)(event.target.value)}
            >
              <option value="">The transcript&apos;s language</option>
              {(languages.data ?? []).map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </NativeSelect>
          </Field>
        )}
        <ToggleRow
          label="Long pauses"
          checked={pauses}
          onCheckedChange={option(setPauses)}
        />
        {pauses && (
          <PanelSlider
            label="Pause threshold"
            display={`${threshold.toFixed(1)} s`}
            min={PAUSE_MIN_S}
            max={PAUSE_MAX_S}
            step={0.1}
            value={threshold}
            onChange={option(setThreshold)}
          />
        )}
        <ToggleRow
          label="Bad takes"
          hint="Repeated or abandoned sentences, found by the AI"
          checked={badTakes}
          onCheckedChange={option(setBadTakes)}
        />
        <Button
          variant="secondary"
          disabled={locked || !(fillers || pauses || badTakes)}
          onClick={() => void search()}
        >
          <MagnifyingGlassIcon aria-hidden />
          Find what to remove
        </Button>
        {find.isPending && (
          <p role="status" className="text-caption text-muted-foreground">
            Looking…
          </p>
        )}
        {preview && items.length === 0 && (
          <p role="status" className="text-body text-muted-foreground">
            Nothing to remove in this clip.
          </p>
        )}
        {items.length > 0 && (
          <>
            <p className="text-caption text-muted-foreground">
              Uncheck what you want to keep.
            </p>
            <CleanupItems
              items={items}
              unchecked={unchecked}
              disabled={locked}
              onToggle={toggle}
            />
            <Button
              disabled={locked || checked === 0}
              onClick={() => void apply()}
            >
              <EraserIcon aria-hidden />
              {checked === 1 ? "Remove 1 cut" : `Remove ${checked} cuts`}
            </Button>
          </>
        )}
        <p className="text-caption text-muted-foreground">
          Render the clip again to see the cuts in the video.
        </p>
      </PanelGroup>
      <EnhanceSection clip={clip} edits={edits} busy={busy} />
    </>
  );
}
