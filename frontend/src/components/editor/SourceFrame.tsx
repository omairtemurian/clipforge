import { CircleNotchIcon } from "@phosphor-icons/react";
import {
  useEffect,
  useRef,
  type HTMLAttributes,
  type ReactNode,
  type RefObject,
} from "react";
import { apiUrl } from "@/api/client";
import { useCropTrack } from "@/api/clips";
import type { Clip, CropTrack } from "@/api/types";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { cn } from "@/lib/utils";

interface CropTrackGateProps {
  clip: Clip;
  edits: ClipEdits;
  children: (track: CropTrack) => ReactNode;
}

/**
 * children with the clip's planned fill window and source frame size
 * (GET /clips/{id}/crop in the edited aspect), once loaded; a spinner
 * before, and a note if the clip has no crop plan.
 */
export function CropTrackGate({ clip, edits, children }: CropTrackGateProps) {
  const track = useCropTrack(clip.id, edits.look.framing.aspect, true);

  if (track.isPending) {
    return (
      <div className="flex items-center gap-2 text-body text-muted-foreground">
        <CircleNotchIcon className="size-5 animate-spin" aria-hidden />
        Loading the crop…
      </div>
    );
  }
  if (track.isError) {
    return (
      <p
        role="alert"
        className="max-w-sm text-center text-body text-muted-foreground"
      >
        The crop tool needs the clip&apos;s crop plan. Process the project again
        to make it.
      </p>
    );
  }
  return <>{children(track.data)}</>;
}

interface SourceFrameProps extends HTMLAttributes<HTMLDivElement> {
  projectId: number;
  /** The source time to show, in seconds. */
  time: number;
  /** The source frame's size in pixels. */
  frame: { width: number; height: number };
  frameRef: RefObject<HTMLDivElement>;
}

/**
 * The project's source video, paused at time, in a box of the frame's
 * aspect that fits its column, with children over it (the crop window or
 * the subject picker); the box's other props (pointer handlers) are
 * passed on.
 */
export function SourceFrame({
  projectId,
  time,
  frame,
  frameRef,
  className,
  style,
  children,
  ...props
}: SourceFrameProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (video && Math.abs(video.currentTime - time) > 0.02) {
      video.currentTime = time;
    }
  }, [time]);

  return (
    <div
      ref={frameRef}
      {...props}
      className={cn(
        "relative max-h-full max-w-full touch-none overflow-hidden rounded-xl bg-black select-none",
        className,
      )}
      style={{
        aspectRatio: `${frame.width} / ${frame.height}`,
        width: frame.width >= frame.height ? "100%" : undefined,
        height: frame.width < frame.height ? "100%" : undefined,
        ...style,
      }}
    >
      <video
        ref={videoRef}
        src={apiUrl(`/media/${projectId}/source`)}
        aria-label="Source video"
        muted
        playsInline
        preload="auto"
        className="pointer-events-none size-full object-contain"
      />
      {children}
    </div>
  );
}
