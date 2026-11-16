import { useEffect, useRef } from "react";
import { ImageIcon } from "@phosphor-icons/react";
import type { LogoPosition } from "@/lib/brandForm";
import { cn } from "@/lib/utils";

const CORNER: Record<LogoPosition, string> = {
  tl: "top-3 left-3",
  tr: "top-3 right-3",
  bl: "bottom-14 left-3",
  br: "bottom-14 right-3",
};

interface BrandPreviewProps {
  name: string;
  position: LogoPosition;
  opacity: number;
  color: string;
  font: string;
  /** A newly picked logo, shown before it is saved. */
  logoFile: File | null;
  /** URL of the saved logo, if the template has one. */
  savedLogoUrl: string | null;
}

/**
 * A 9:16 frame that shows how the brand sits on a clip: the logo in its
 * corner at its opacity, a caption sample in the primary color, and the
 * template name. The picked logo is a blob URL, set on the <img> in an
 * effect so that it is revoked when the file changes.
 */
export function BrandPreview({
  name,
  position,
  opacity,
  color,
  font,
  logoFile,
  savedLogoUrl,
}: BrandPreviewProps) {
  const logoRef = useRef<HTMLImageElement>(null);
  const hasLogo = logoFile !== null || savedLogoUrl !== null;

  useEffect(() => {
    const image = logoRef.current;
    if (!image || !logoFile) return;
    const url = URL.createObjectURL(logoFile);
    image.src = url;
    return () => {
      URL.revokeObjectURL(url);
      if (savedLogoUrl) image.src = savedLogoUrl;
    };
  }, [logoFile, savedLogoUrl]);

  return (
    <figure className="flex w-44 shrink-0 flex-col gap-2">
      <div
        data-testid="brand-preview"
        className="relative aspect-[9/16] overflow-hidden rounded-2xl border border-border bg-muted"
      >
        {hasLogo ? (
          <img
            ref={logoRef}
            src={savedLogoUrl ?? undefined}
            alt="Logo preview"
            data-position={position}
            style={{ opacity }}
            className={cn(
              "absolute max-h-14 max-w-[40%] object-contain",
              CORNER[position],
            )}
          />
        ) : (
          <div
            className={cn(
              "absolute flex size-10 items-center justify-center rounded-md border border-dashed border-border text-muted-foreground",
              CORNER[position],
            )}
          >
            <ImageIcon className="size-4" aria-hidden />
          </div>
        )}
        <p
          className="absolute inset-x-3 bottom-24 text-center text-base leading-tight font-extrabold uppercase"
          style={{ color }}
        >
          Your words here
        </p>
        <div
          className="absolute inset-x-0 bottom-0 flex h-9 items-center justify-center text-[11px] font-semibold text-background"
          style={{ backgroundColor: color }}
        >
          <span className="truncate px-2">
            {name.trim() || "Template name"}
          </span>
        </div>
      </div>
      <figcaption className="text-center text-caption text-muted-foreground">
        Preview · {font}
      </figcaption>
    </figure>
  );
}
