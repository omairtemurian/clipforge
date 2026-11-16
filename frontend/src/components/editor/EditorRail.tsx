import {
  ClosedCaptioningIcon,
  FilmSlateIcon,
  GaugeIcon,
  ImagesIcon,
  IntersectIcon,
  LayoutIcon,
  LightningIcon,
  ListChecksIcon,
  ListNumbersIcon,
  MusicNotesIcon,
  SparkleIcon,
  StampIcon,
  TextAaIcon,
  TextTIcon,
  WaveformIcon,
} from "@phosphor-icons/react";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import { useState } from "react";
import type { Clip, Project, Word } from "@/api/types";
import { AudioPanel } from "@/components/AudioPanel";
import { BrollPanel } from "@/components/BrollPanel";
import { CleanupPanel } from "@/components/CleanupPanel";
import { BrandPanel } from "@/components/editor/BrandPanel";
import { CaptionsPanel } from "@/components/editor/CaptionsPanel";
import { LayoutPanel } from "@/components/editor/LayoutPanel";
import { HookPanel } from "@/components/HookPanel";
import { MotionGraphicsPanel } from "@/components/MotionGraphicsPanel";
import { TextPanel } from "@/components/editor/TextPanel";
import { MediaLibrary } from "@/components/MediaLibrary";
import { TextOverlayPanel } from "@/components/TextOverlayPanel";
import { TransitionPicker } from "@/components/TransitionPicker";
import { SectionMenu } from "@/components/timeline/SectionMenu";
import { RuleCheckPanel } from "@/components/RuleCheckPanel";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";
import { Panel } from "@/components/ui/panel";
import type { ClipEdits } from "@/hooks/useClipEdits";
import type { SceneEdits } from "@/hooks/useSceneEdits";
import type { SceneTracker } from "@/hooks/useSceneTrack";
import { SCORE_TEXT, scoreTone } from "@/lib/clips";
import { layerLength } from "@/lib/layers";
import { sourceToPreview } from "@/lib/timeline";
import { cn } from "@/lib/utils";

type PanelName =
  | "Captions"
  | "Layout"
  | "Sections"
  | "Transitions"
  | "Hooks"
  | "Graphics"
  | "Cleanup"
  | "Audio"
  | "B-roll"
  | "Brand"
  | "Text"
  | "Text layers"
  | "Media"
  | "Score"
  | "Rules";

const PANELS: { name: PanelName; icon: PhosphorIcon }[] = [
  { name: "Captions", icon: ClosedCaptioningIcon },
  { name: "Layout", icon: LayoutIcon },
  { name: "Sections", icon: ListNumbersIcon },
  { name: "Transitions", icon: IntersectIcon },
  { name: "Hooks", icon: LightningIcon },
  { name: "Graphics", icon: SparkleIcon },
  { name: "Cleanup", icon: WaveformIcon },
  { name: "Audio", icon: MusicNotesIcon },
  { name: "B-roll", icon: FilmSlateIcon },
  { name: "Brand", icon: StampIcon },
  { name: "Text", icon: TextTIcon },
  { name: "Text layers", icon: TextAaIcon },
  { name: "Media", icon: ImagesIcon },
  { name: "Score", icon: GaugeIcon },
  { name: "Rules", icon: ListChecksIcon },
];

interface EditorRailProps {
  clip: Clip;
  edits: ClipEdits;
  scenes: SceneEdits;
  tracker: SceneTracker;
  /** The clip's transcript words (with context), once loaded. */
  words: Word[] | undefined;
  /** The clip's project, once loaded (its brand template). */
  project: Project | undefined;
  /** The playhead, in source seconds. */
  playhead: number;
  /** A save or render is under way (the section edits wait for it). */
  busy: boolean;
  /** The timeline's selected layer item, and selecting one. */
  selectedItem: string | null;
  onSelectItem: (id: string) => void;
}

function ScorePanel({ clip }: { clip: Clip }) {
  const { overall } = clip.scores;
  return (
    <div>
      <p
        className={cn(
          "mb-4 text-4xl font-bold tabular-nums",
          SCORE_TEXT[scoreTone(overall)],
        )}
      >
        {overall}
      </p>
      <ScoreBreakdown clip={clip} />
    </div>
  );
}

/**
 * The editor's right column: a rail of labeled icons, each opening its
 * panel in a drawer beside the rail (Captions, Layout, Sections,
 * Transitions, "Hooks": the viral hook and headline, "Graphics": the motion
 * graphics, "Cleanup": speech cleanup and enhancement, "Audio": music, sound
 * effects, "B-roll": stock video cutaways and picture-in-picture, Brand,
 * Text, "Text layers": the text overlays, "Media": the media library to drag onto the timeline, "Score": the clip's virality
 * score and why it was picked, and "Rules": the campaign rule check of the
 * saved clip). Clicking the open panel's icon closes it.
 */
export function EditorRail({
  clip,
  edits,
  scenes,
  tracker,
  words,
  project,
  playhead,
  busy,
  selectedItem,
  onSelectItem,
}: EditorRailProps) {
  const [open, setOpen] = useState<PanelName | null>(null);
  const at = sourceToPreview(playhead, edits.range, edits.cuts);
  const length = layerLength(edits.range, edits.cuts);

  return (
    <div className="flex h-full">
      {open && (
        <aside
          aria-label={`${open} panel`}
          className="w-80 overflow-y-auto border-l border-border bg-card/40 p-5"
        >
          <Panel title={open}>
            {open === "Captions" && (
              <CaptionsPanel clip={clip} edits={edits} words={words} />
            )}
            {open === "Layout" && (
              <LayoutPanel
                clipId={clip.id}
                edits={edits}
                scenes={scenes}
                tracker={tracker}
                project={project}
              />
            )}
            {open === "Sections" && (
              <SectionMenu
                clip={clip}
                edits={edits}
                playhead={playhead}
                busy={busy}
              />
            )}
            {open === "Transitions" && (
              <TransitionPicker
                transitions={edits.transitions}
                sectionCount={clip.segments.length}
                onChange={edits.setTransitions}
              />
            )}
            {open === "Hooks" && (
              <HookPanel clip={clip} edits={edits} busy={busy} />
            )}
            {open === "Graphics" && (
              <MotionGraphicsPanel
                clip={clip}
                edits={edits}
                busy={busy}
                selectedItem={selectedItem}
                onSelectItem={onSelectItem}
              />
            )}
            {open === "Cleanup" && (
              <CleanupPanel clip={clip} edits={edits} busy={busy} />
            )}
            {open === "Audio" && (
              <AudioPanel
                clip={clip}
                edits={edits}
                busy={busy}
                at={at}
                length={length}
                selectedItem={selectedItem}
                onSelectItem={onSelectItem}
              />
            )}
            {open === "B-roll" && (
              <BrollPanel
                clip={clip}
                edits={edits}
                busy={busy}
                selectedItem={selectedItem}
                onSelectItem={onSelectItem}
              />
            )}
            {open === "Brand" && project && <BrandPanel project={project} />}
            {open === "Text" && <TextPanel clip={clip} edits={edits} />}
            {open === "Text layers" && (
              <TextOverlayPanel
                layers={edits.layers}
                at={at}
                length={length}
                onChange={(items, gesture) =>
                  edits.setLayer("text", items, gesture)
                }
                selectedItem={selectedItem}
                onSelectItem={onSelectItem}
              />
            )}
            {open === "Media" && (
              <MediaLibrary
                layers={edits.layers}
                at={at}
                length={length}
                onAdd={(name, items) => edits.setLayer(name, items)}
                onSelectItem={onSelectItem}
              />
            )}
            {open === "Score" && <ScorePanel clip={clip} />}
            {open === "Rules" && <RuleCheckPanel clipId={clip.id} />}
          </Panel>
        </aside>
      )}
      <nav
        aria-label="Editor panels"
        className="flex w-[72px] flex-col items-center gap-0.5 overflow-y-auto border-l border-border py-2"
      >
        {PANELS.map(({ name, icon: Icon }) => (
          <button
            key={name}
            type="button"
            aria-pressed={open === name}
            onClick={() => setOpen(open === name ? null : name)}
            className={cn(
              "flex w-16 shrink-0 flex-col items-center gap-0.5 rounded-lg py-1.5 text-center text-micro leading-tight text-muted-foreground cursor-pointer transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50",
              open === name && "bg-muted text-foreground",
            )}
          >
            <Icon className="size-5" aria-hidden />
            {name}
          </button>
        ))}
      </nav>
    </div>
  );
}
