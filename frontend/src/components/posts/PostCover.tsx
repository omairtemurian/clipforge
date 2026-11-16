import { CircleNotchIcon, ImageSquareIcon } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type RefObject } from "react";
import {
  coverUrl,
  frameUrl,
  usePickFrame,
  useUploadCover,
} from "@/api/thumbnails";
import type { Asset, Clip } from "@/api/types";
import { Button } from "@/components/ui/button";
import { clipSeconds } from "@/lib/postCopy";

interface PostCoverProps {
  clip: Clip;
  cover: Asset | null;
  onCover: (cover: Asset) => void;
}

/** How long the slider rests before the preview asks for its frame. */
const SETTLE_MS = 250;

/**
 * The cover of the clip's posts: a slider over the rendered video with the
 * frame at that time, "Use this frame", or an uploaded JPEG or PNG. The
 * cover applies to every platform's post of this modal.
 */
export function PostCover({ clip, cover, onCover }: PostCoverProps) {
  const rendered = clip.status === "rendered";
  const length = Math.max(0, clipSeconds(clip) - 0.2);
  const [time, setTime] = useState(0);
  const [shown, setShown] = useState(0);
  const [broken, setBroken] = useState(false);
  const pick = usePickFrame(clip.id);
  const upload = useUploadCover(clip.id);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setShown(time);
      setBroken(false);
    }, SETTLE_MS);
    return () => clearTimeout(timer);
  }, [time]);

  if (!rendered) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-dashed border-border p-3 text-sm text-muted-foreground">
        Render the clip to choose a cover frame, or upload an image.
        <UploadButton file={file} busy={upload.isPending} />
        <CoverFile
          file={file}
          onFile={(f) => upload.mutate(f, { onSuccess: onCover })}
        />
        {cover && <ChosenCover cover={cover} />}
      </div>
    );
  }

  return (
    <section
      aria-label="Cover"
      className="flex flex-wrap items-center gap-4 rounded-xl border border-border p-3"
    >
      <div className="aspect-[9/16] w-16 shrink-0 overflow-hidden rounded-md bg-muted">
        {!broken && (
          <img
            src={frameUrl(clip.id, shown)}
            alt={`Frame at ${shown.toFixed(1)} seconds`}
            onError={() => setBroken(true)}
            className="size-full object-cover"
          />
        )}
      </div>
      <div className="flex min-w-48 flex-1 flex-col gap-2">
        <label htmlFor="cover-time" className="text-sm font-medium">
          Cover frame
          <span className="ml-2 text-xs text-muted-foreground tabular-nums">
            {time.toFixed(1)} s
          </span>
        </label>
        <input
          id="cover-time"
          type="range"
          min={0}
          max={length}
          step={0.1}
          value={Math.min(time, length)}
          onChange={(event) => setTime(Number(event.target.value))}
          className="w-full accent-primary"
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={pick.isPending}
            onClick={() => pick.mutate(time, { onSuccess: onCover })}
          >
            {pick.isPending && (
              <CircleNotchIcon className="animate-spin" aria-hidden />
            )}
            Use this frame
          </Button>
          <UploadButton file={file} busy={upload.isPending} />
          <CoverFile
            file={file}
            onFile={(f) => upload.mutate(f, { onSuccess: onCover })}
          />
        </div>
      </div>
      {cover && <ChosenCover cover={cover} />}
    </section>
  );
}

function UploadButton({
  file,
  busy,
}: {
  file: RefObject<HTMLInputElement>;
  busy: boolean;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      disabled={busy}
      onClick={() => file.current?.click()}
    >
      {busy ? (
        <CircleNotchIcon className="animate-spin" aria-hidden />
      ) : (
        <ImageSquareIcon aria-hidden />
      )}
      Upload image
    </Button>
  );
}

function CoverFile({
  file,
  onFile,
}: {
  file: RefObject<HTMLInputElement>;
  onFile: (file: File) => void;
}) {
  return (
    <input
      ref={file}
      type="file"
      accept="image/jpeg,image/png"
      aria-label="Cover image"
      hidden
      onChange={(event) => {
        const picked = event.target.files?.[0];
        if (picked) onFile(picked);
        event.target.value = "";
      }}
    />
  );
}

function ChosenCover({ cover }: { cover: Asset }) {
  return (
    <figure className="w-16 shrink-0">
      <img
        src={coverUrl(cover.id)}
        alt="Chosen cover"
        className="aspect-[9/16] w-full rounded-md object-cover"
      />
      <figcaption className="mt-1 text-center text-xs text-muted-foreground">
        Chosen
      </figcaption>
    </figure>
  );
}
