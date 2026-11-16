import {
  ArrowLeftIcon,
  ArrowUUpLeftIcon,
  ArrowUUpRightIcon,
  CircleNotchIcon,
  ClockCounterClockwiseIcon,
  CloudIcon,
  CloudSlashIcon,
  DownloadSimpleIcon,
  FilmSlateIcon,
  FloppyDiskIcon,
} from "@phosphor-icons/react";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiUrl } from "@/api/client";
import type { Clip } from "@/api/types";
import { backLink } from "@/lib/editorBack";
import { PostButton } from "@/components/posts/PostButton";
import { VersionHistoryDialog } from "@/components/editor/VersionHistory";
import { ProEditButton } from "@/features/proedit";
import { Button } from "@/components/ui/button";
import type { Autosave, AutosaveStatus } from "@/hooks/useAutosave";
import type { ClipExport } from "@/hooks/useClipExport";
import type { Undo } from "@/hooks/useUndo";

interface EditorTopBarProps {
  clip: Clip;
  /** The clip's title as edited now. */
  title: string;
  /** Undo/redo and the version history. */
  undo: Undo;
  autosave: Autosave;
  /** The edits differ from the saved clip. */
  dirty: boolean;
  /** The edits cannot be saved (a text is too long, too few hashtags). */
  invalid: boolean;
  /** Save, render and download of the clip. */
  exporter: ClipExport;
}

const ICON_BUTTON =
  "inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-40";

const AUTOSAVE_TEXT: Record<AutosaveStatus, string> = {
  off: "Autosave off",
  saved: "All changes saved",
  pending: "Unsaved changes",
  saving: "Saving…",
  failed: "Autosave failed",
};

function IconButton({
  label,
  title,
  icon: Icon,
  enabled = true,
  pressed,
  onClick,
}: {
  label: string;
  title: string;
  icon: PhosphorIcon;
  enabled?: boolean;
  pressed?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={title}
      aria-pressed={pressed}
      disabled={!enabled}
      onClick={onClick}
      className={ICON_BUTTON}
    >
      <Icon className="size-4" aria-hidden />
    </button>
  );
}

function renderLabel({ rendering, progress }: ClipExport): string {
  if (!rendering) return "Render";
  return progress === null
    ? "Rendering…"
    : `Rendering ${Math.round(progress * 100)}%`;
}

/** The editor's top bar: back to the project's clips (or to the page that
 * opened it, see backLink), the clip title,
 * the autosave status and on/off toggle, undo/redo (useUndo), "Version
 * history" (restore a saved version), "Save changes" (while there are
 * edits), "Render" (saves first), once the clip is rendered, "Download",
 * "Pro Edit" (its variants, while Pro Edit is enabled) and "Post" (the
 * "Schedule post" modal). */
export function EditorTopBar({
  clip,
  title,
  undo,
  autosave,
  dirty,
  invalid,
  exporter,
}: EditorTopBarProps) {
  const busy = exporter.saving || exporter.rendering;
  const [versionsOpen, setVersionsOpen] = useState(false);
  const back = backLink(useLocation().state, clip.project_id);
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-4">
      <Link to={back.to} aria-label={back.label} className={ICON_BUTTON}>
        <ArrowLeftIcon className="size-4" aria-hidden />
      </Link>
      <h1 className="min-w-0 truncate text-section font-medium" title={title}>
        {title}
      </h1>
      <div className="ml-auto flex items-center gap-1">
        <p
          role="status"
          aria-label="Autosave status"
          className="mr-1 text-caption whitespace-nowrap text-muted-foreground"
        >
          {AUTOSAVE_TEXT[autosave.status]}
        </p>
        <IconButton
          label="Autosave"
          title={autosave.on ? "Turn autosave off" : "Turn autosave on"}
          icon={autosave.on ? CloudIcon : CloudSlashIcon}
          pressed={autosave.on}
          onClick={autosave.toggle}
        />
        <IconButton
          label="Undo"
          title="Undo (⌘Z)"
          icon={ArrowUUpLeftIcon}
          enabled={undo.canUndo}
          onClick={undo.undo}
        />
        <IconButton
          label="Redo"
          title="Redo (⇧⌘Z)"
          icon={ArrowUUpRightIcon}
          enabled={undo.canRedo}
          onClick={undo.redo}
        />
        <IconButton
          label="Version history"
          title="Version history"
          icon={ClockCounterClockwiseIcon}
          onClick={() => setVersionsOpen(true)}
        />
        {versionsOpen && (
          <VersionHistoryDialog
            undo={undo}
            dirty={dirty}
            busy={busy}
            onClose={() => setVersionsOpen(false)}
          />
        )}
        <Button
          variant="outline"
          className="ml-2"
          disabled={!dirty || invalid || busy}
          title={invalid ? "Fix the texts first" : undefined}
          onClick={() => void exporter.save()}
        >
          {exporter.saving ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <FloppyDiskIcon aria-hidden />
          )}
          Save changes
        </Button>
        {exporter.downloadable && (
          <Button variant="outline" asChild>
            <a
              href={apiUrl(`/clips/${clip.id}/download`)}
              title="Download the rendered video"
            >
              <DownloadSimpleIcon aria-hidden />
              Download
            </a>
          </Button>
        )}
        <ProEditButton clip={clip} />
        <PostButton
          clip={clip}
          disabled={dirty}
          title={
            dirty ? "Save the changes first" : "Post to your default accounts"
          }
        />
        <Button
          disabled={invalid || busy}
          title={invalid ? "Fix the texts first" : undefined}
          onClick={() => void exporter.render()}
        >
          {exporter.rendering ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <FilmSlateIcon aria-hidden />
          )}
          {renderLabel(exporter)}
        </Button>
      </div>
    </header>
  );
}
