import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useClip, useClipTranscript } from "@/api/clips";
import { useProject } from "@/api/projects";
import type { Clip, Project } from "@/api/types";
import { EditorRail } from "@/components/editor/EditorRail";
import { PreviewColumn } from "@/components/editor/PreviewColumn";
import { TimelinePanel } from "@/components/editor/TimelinePanel";
import { EditorTopBar } from "@/components/editor/TopBar";
import { TranscriptColumn } from "@/components/editor/TranscriptColumn";
import { Button } from "@/components/ui/button";
import { useAutosave } from "@/hooks/useAutosave";
import { useClipEdits } from "@/hooks/useClipEdits";
import { useClipExport } from "@/hooks/useClipExport";
import { useSceneEdits } from "@/hooks/useSceneEdits";
import { useSceneTrack } from "@/hooks/useSceneTrack";
import { usePreviewPlayer } from "@/hooks/usePreviewPlayer";
import { useTimelineKeys } from "@/hooks/useTimelineKeys";
import { useTimelineState } from "@/hooks/useTimelineState";
import { useUndo } from "@/hooks/useUndo";
import type { SceneChoice } from "@/lib/scenes";
import { textProblems } from "@/lib/clipText";
import type { WordSelection } from "@/lib/cuts";
import {
  contextWindow,
  previewToSource,
  sourceToPreview,
} from "@/lib/timeline";
import { timelineActions } from "@/lib/timelineActions";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * The clip editor (3 columns over the timeline): the clip's transcript
 * left, its preview in the center and the panel rail right. The timeline
 * shows the clip within 30 s of source around it; dragging its handles
 * trims or extends the clip, and the playhead follows the preview (whose
 * time has the saved cut ranges removed). Edits autosave once they rest
 * (useAutosave; top bar toggle) and undo/redo (top bar, cmd+Z /
 * shift+cmd+Z) goes past them into the clip's saved versions (useUndo),
 * which "Version history" lists and restores. The keyboard
 * (useTimelineKeys): Space plays or pauses, Delete removes the selected
 * layer item or cuts the selected words or segment, S splits the clip at
 * the playhead, +/- zoom the timeline, the arrows step the playhead a
 * frame (shift: 1 s), < / > change the playback speed and cmd+C / cmd+V
 * copy a layer item and paste it at the playhead.
 * The clip's scenes (useSceneEdits) split the segment row too; the Layout
 * panel frames the scene at the playhead, and a fixed or tracked scene's
 * keyframes show under the segment row. The layer tracks (B-roll,
 * overlays, text, music, SFX, voiceover) sit around the video row; dragging
 * their items moves or trims them (snapped unless snapping is off), saved
 * with the other edits. The rail's Sections panel (SectionMenu) rearranges,
 * adds, deletes and splits the clip's sections and duplicates or splits the
 * clip itself. Its Media panel drags library files onto the layer tracks,
 * its Text layers panel adds and styles text overlays and its Transitions
 * panel sets the transitions at jump cuts and between sections (all saved
 * with the other edits). Tracking a subject
 * (useSceneTrack) saves the clip, so the preview shows it.
 * The rail's Captions and Layout panels and the player toolbar (aspect,
 * layout, crop tool) and the Layout panel's custom ratio edit the clip's
 * look the same way, and its Text panel
 * the title, hook, description and hashtags. The top bar saves the edits
 * (PATCH), renders the clip and downloads the video; the Brand panel
 * saves the project's brand template at once.
 */
function ClipEditor({ clip, project }: { clip: Clip; project?: Project }) {
  const duration = project?.duration ?? 0;
  const aspect = project?.settings.aspect ?? "9:16";
  const edits = useClipEdits(clip);
  const exporter = useClipExport(clip, edits);
  const [selection, setSelection] = useState<WordSelection | null>(null);
  const words = useClipTranscript(clip.id).data;
  const player = usePreviewPlayer();
  const timeline = useTimelineState();

  const view = contextWindow(clip, duration);
  const playhead = previewToSource(player.time, clip, clip.cut_ranges);
  const seek = (t: number) =>
    player.seek(sourceToPreview(t, clip, clip.cut_ranges));
  const scenes = useSceneEdits(clip.id, edits, playhead);
  const [tracked, setTracked] = useState(0);
  const tracker = useSceneTrack(clip.id, scenes, () =>
    setTracked((n) => n + 1),
  );
  const { save } = exporter;
  useEffect(() => {
    if (tracked > 0) void save();
    // Saves once per track, after the render that holds its keyframes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tracked]);
  const busy = exporter.saving || exporter.rendering;
  const undo = useUndo(clip.id, edits, busy);
  const invalid = Object.keys(textProblems(edits.texts)).length > 0;
  const autosave = useAutosave({
    dirty: edits.dirty,
    edits: JSON.stringify([edits.patch, edits.layers]),
    blocked: invalid || busy || undo.moving,
    saving: exporter.saving,
    save,
  });
  const actions = timelineActions({
    edits,
    sceneBounds: scenes.bounds,
    timeline,
    words,
    selection,
    clearSelection: () => setSelection(null),
    playhead,
    seek,
    previewTime: player.time,
    seekPreview: player.seek,
  });
  const selectWords = (next: WordSelection | null) => {
    setSelection(next);
    if (next) {
      timeline.select(null);
      timeline.selectItem(null);
    }
  };
  const keys = useTimelineKeys({
    edits,
    actions,
    timeline,
    player,
    undo,
    playhead,
    clearWords: () => setSelection(null),
  });

  const picked = actions.selected;
  const segmentOverride = picked
    ? {
        value: scenes.choiceAt(picked),
        onChoose: (choice: SceneChoice) => scenes.chooseAt(picked, choice),
      }
    : undefined;

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <EditorTopBar
        clip={clip}
        title={edits.texts.title}
        undo={undo}
        autosave={autosave}
        dirty={edits.dirty}
        invalid={invalid}
        exporter={exporter}
      />
      <div className="flex min-h-0 flex-1">
        <div className="w-[45%] shrink-0 overflow-hidden border-r border-border">
          <TranscriptColumn
            clip={clip}
            edits={edits}
            bounds={view}
            selection={selection}
            onSelect={selectWords}
            onSeek={seek}
            onDelete={actions.deleteSelection}
            playhead={playhead}
            playing={player.playing}
          />
        </div>
        <PreviewColumn
          clip={clip}
          edits={edits}
          projectAspect={aspect}
          player={player}
          playhead={playhead}
          scenes={scenes}
          tracker={tracker}
        />
        <EditorRail
          clip={clip}
          edits={edits}
          scenes={scenes}
          tracker={tracker}
          words={words}
          project={project}
          playhead={playhead}
          busy={busy}
          selectedItem={timeline.item}
          onSelectItem={keys.selectItem}
        />
      </div>
      <TimelinePanel
        clipId={clip.id}
        saved={clip}
        timeline={timeline}
        player={player}
        view={view}
        clip={edits.range}
        cuts={edits.cuts}
        splits={edits.splits}
        parts={actions.parts}
        selected={actions.selected}
        labelAt={scenes.labelAt}
        override={segmentOverride}
        keyframes={scenes.keyframeRow(seek)}
        playhead={playhead}
        snapWords={timeline.snap ? (words ?? []) : []}
        layers={edits.layers}
        onLayerChange={edits.setLayer}
        selectedItem={timeline.item}
        onSelectItem={keys.selectItem}
        onChange={edits.setRange}
        onSeek={seek}
        onSelect={(part) => {
          timeline.select(part);
          setSelection(null);
          if (playhead < part[0] || playhead >= part[1]) seek(part[0]);
        }}
        onSplit={actions.split}
        canDelete={keys.canDelete}
        onDelete={keys.deleteSelection}
        onSkip={actions.skip}
      />
    </div>
  );
}

function EditorSkeleton() {
  return (
    <div className="flex h-screen flex-col gap-4 bg-background p-6">
      <Skeleton className="h-8 w-1/3 rounded-lg" />
      <Skeleton className="flex-1 rounded-xl bg-muted/50" />
    </div>
  );
}

/** The editor once the clip's project (its duration and aspect) is loaded;
 * without it the timeline is not bounded by the video's end. */
function ProjectClipEditor({ clip }: { clip: Clip }) {
  const project = useProject(clip.project_id);
  if (project.isPending) return <EditorSkeleton />;
  return <ClipEditor clip={clip} project={project.data} />;
}

/** The route /clips/:clipId: the editor once the clip is loaded. */
export function EditorPage() {
  const id = Number(useParams().clipId);
  const clip = useClip(id);

  if (clip.isPending) return <EditorSkeleton />;
  if (clip.isError) {
    return (
      <div className="flex h-screen flex-col items-start gap-3 bg-background p-10 text-body text-muted-foreground">
        <p>Could not load this clip.</p>
        <Button variant="outline" asChild>
          <Link to="/projects">Back to projects</Link>
        </Button>
      </div>
    );
  }
  return <ProjectClipEditor key={clip.data.id} clip={clip.data} />;
}
