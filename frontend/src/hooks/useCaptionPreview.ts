import { useEffect, useState } from "react";
import { fetchCaptionPreview } from "@/api/captions";
import type { CaptionStyle } from "@/api/types";

/** How long the style must stay unchanged before its preview is drawn. */
export const PREVIEW_DELAY_MS = 300;

export interface CaptionPreviewState {
  /** An object URL of the latest preview PNG, null until one is drawn. */
  url: string | null;
  /** Whether the backend could not draw the latest style. */
  failed: boolean;
}

/**
 * The live preview of template name with style: the backend draws the
 * template's sample caption with the style (POST /caption-templates/{name}/
 * preview) once the style has not changed for PREVIEW_DELAY_MS; a newer
 * style cancels the older request. Without a name nothing is drawn.
 */
export function useCaptionPreview(
  name: string | undefined,
  style: CaptionStyle,
): CaptionPreviewState {
  const [state, setState] = useState<CaptionPreviewState>({
    url: null,
    failed: false,
  });
  const key = JSON.stringify(style);

  useEffect(() => {
    if (!name) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      fetchCaptionPreview(
        name,
        JSON.parse(key) as CaptionStyle,
        controller.signal,
      )
        .then((png) =>
          setState({ url: URL.createObjectURL(png), failed: false }),
        )
        .catch(() => {
          if (!controller.signal.aborted) {
            setState((previous) => ({ ...previous, failed: true }));
          }
        });
    }, PREVIEW_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [name, key]);

  useEffect(
    () => () => {
      if (state.url) URL.revokeObjectURL(state.url);
    },
    [state.url],
  );

  return state;
}
